# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

from machine import Pin
from rotation_handler import RotationHandler, Quadrature, CW, CCW
import uasyncio as asyncio


class GarageDoor:
    def __init__(self, relay_pin, relay_trigger_ms, opened_pin, closed_pin, hall_1_pin, hall_2_pin, num_rotations,
                 open_is_cw, quadrature=False):
        self.relay_pin = relay_pin
        self.relay_trigger_ms = relay_trigger_ms
        self.opened_pin = opened_pin
        self.closed_pin = closed_pin
        self.relay = Pin(relay_pin, Pin.OUT, value=1)  # my relay will trigger after a reboot if I don't set this high
        self.opened = Pin(opened_pin, Pin.IN, pull=Pin.PULL_UP)
        self.closed = Pin(closed_pin, Pin.IN, pull=Pin.PULL_UP)
        self.open_direction = CW if open_is_cw else CCW
        self.close_direction = CCW if open_is_cw else CW
        self.last_state = None
        self.last_command = None
        self.last_percent_open = None

        self.hall_1_pin = hall_1_pin
        self.hall_2_pin = hall_2_pin
        if quadrature:
            self.rotation_handler = Quadrature(self.hall_1_pin,
                                               self.hall_2_pin,
                                               num_rotations)
        else:
            self.rotation_handler = RotationHandler(self.hall_1_pin,
                                                    self.hall_2_pin,
                                                    num_rotations)

    async def trigger_relay(self):
        self.relay.off()
        await asyncio.sleep_ms(self.relay_trigger_ms)
        self.relay.on()

    def is_fully_opened(self):
        return self.opened.value() == 0

    def is_fully_closed(self):
        return self.closed.value() == 0

    def is_opening(self):
        return self.rotation_handler.movement == self.open_direction

    def is_closing(self):
        return self.rotation_handler.movement == self.close_direction

    def is_stopped(self):
        return not self.rotation_handler.is_moving()

    def update(self):
        """Recalculates state and position based on the current data and returns the state and percent open if they have
         changed since the last update()."""
        current_state = None
        current_percent_open = None

        if self.is_fully_closed():
            current_state = 'closed'
            current_percent_open = 0
            self.rotation_handler.reset()
        elif self.is_fully_opened():
            current_state = 'open'
            current_percent_open = 100
            self.rotation_handler.reset()
        elif self.is_stopped():
            current_state = 'stopped'
        elif self.is_opening() or self.is_closing():
            current_state = 'opening' if self.is_opening() else 'closing'
            rotation_done = self.rotation_handler.get_percent_done()
            print("{}, percent done is: {}".format(current_state, rotation_done))
            if rotation_done < 0:
                current_percent_open = abs(rotation_done)
            else:
                current_percent_open = 100 - rotation_done

        if current_state != self.last_state:
            self.last_state = current_state
        else:
            current_state = None
        if current_percent_open != self.last_percent_open:
            self.last_percent_open = current_percent_open
        else:
            current_percent_open = None
        return current_state, current_percent_open

    def update_num_rotations(self, new_value):
        self.rotation_handler.full_motion_rotations = new_value

    async def open(self):
        print("Garage: open() called.")
        if not self.is_fully_opened():
            self.last_command = 'open'
            await self.trigger_relay()

    async def close(self):
        if not self.is_fully_closed():
            self.last_command = 'close'
            await self.trigger_relay()

    async def stop(self):
        if self.is_fully_closed() or self.is_fully_opened():
            print("No need to stop since it's not moving")
        else:
            await self.trigger_relay()

    def __str__(self) -> str:
        return "Garage: {}".format(self.last_state)
