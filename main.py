# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

import json

import uasyncio as asyncio

from mqtt_as import MQTTClient
from mqtt_local import config
from garage_door import GarageDoor

BASE_TOPIC = 'esp32/garage'
STATE_TOPIC = f'{BASE_TOPIC}/{{}}/state'
POSITION_TOPIC = f'{BASE_TOPIC}/{{}}/position'
COMMAND_TOPIC = f'{BASE_TOPIC}/{{}}/set'
CONFIG_TOPIC = f'{BASE_TOPIC}/config'
AVAILABLE_TOPIC = f'{BASE_TOPIC}/availability'

# A config file defines the garage doors, pins, direction of rotation
with open("config.json") as config_file:
    garage_config = json.load(config_file)

# Some config can be updated via MQTT for convenience
updatable_config = {"relay_ms": 500, "full_rotations": 22}

garage_doors = []
for door_config in garage_config['garageDoors']:
    garage_doors.append(
        GarageDoor(door_config['relayPin'], updatable_config['relay_ms'], door_config['closedPin'],
                   door_config['openPin'], door_config['hall1Pin'], door_config['hall2Pin'],
                   updatable_config['full_rotations'], door_config['clockwiseOpen'], door_config['quadrature']))

client = None
command = None
last_state = None


def handle_incoming_message(topic, msg, retained):
    print(f'{topic}: {msg}')
    msg_string = str(msg, 'UTF-8')
    topic_str = str(topic, 'UTF-8')
    if topic_str == CONFIG_TOPIC:
        global updatable_config
        updatable_config = json.loads(msg_string)
        for door in garage_doors:
            door.update_num_rotations(updatable_config['full_rotations'])
    elif topic_str.endswith('/set'):
        global command
        door_index = topic_str.split('/')[-2]
        command = (int(door_index), msg_string)


async def wifi_han(state):
    print('Wifi is ', 'up' if state else 'down')
    await asyncio.sleep(1)


# If you connect with clean_session True, must re-subscribe (MQTT spec 3.1.2.4)
async def conn_han(client):
    await client.subscribe(COMMAND_TOPIC.format('+'), 0)
    await client.subscribe(CONFIG_TOPIC, 0)
    await online()


async def online():
    await client.publish(AVAILABLE_TOPIC, 'online', retain=True, qos=0)


async def process_command():
    global command
    print("Processing {} command...".format(command))
    if command:
        door = garage_doors[command[0]]
        action = command[1]
        if action == 'open' and not door.last_state == 'opening' and not door.is_fully_opened():
            await door.open()
        elif action == 'close' and not door.last_state == 'closing' and not door.is_fully_closed():
            await door.close()
        elif action == 'stop' and door.last_state in ['closing', 'opening']:
            await door.stop()
        command = None


async def main():
    await client.connect()
    await asyncio.sleep(2)  # Give broker time
    await online()
    while True:
        if command:
            await process_command()
        for index in range(len(garage_doors)):
            door = garage_doors[index]
            new_state, new_percent_open = door.update()
            print("New state: {}, New % open: {}".format(new_state, new_percent_open))
            if new_state:
                await client.publish(STATE_TOPIC.format(index), new_state, retain=True)
            if new_percent_open is not None:
                await client.publish(POSITION_TOPIC.format(index), str(new_percent_open), retain=True)
            print("Garage state: {}".format(door))
            print("Fully open?: {}".format(door.is_fully_opened()))
            print("Fully closed?: {}".format(door.is_fully_closed()))
        await asyncio.sleep(0.5)


config['subs_cb'] = handle_incoming_message
config['connect_coro'] = conn_han
config['wifi_coro'] = wifi_han
config['will'] = [AVAILABLE_TOPIC, 'offline', True, 0]

MQTTClient.DEBUG = False
client = MQTTClient(config)

try:
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
finally:
    client.close()
    asyncio.stop()
