# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

from machine import Pin
import utime as time

STOPPED = 'stopped'
CW = 'clockwise'
CCW = 'counter'

AON = 1
AOFF = 0
BON = 3
BOFF = 2

TRANSITION_MAP = {BON: {AON: CCW, AOFF: CW},
                  AON: {BOFF: CCW, BON: CW},
                  BOFF: {AOFF: CCW, AON: CW},
                  AOFF: {BON: CCW, BOFF: CW}}

# TODO: Rotation base class?


class Quadrature:
    """Tracks when a pair of magnets go in and out of range of a pair of hall effect sensors that are positioned to
    achieve a quadrature encoding (A on, B on, A off, B off).  Direction can be determined with a simple dictionary
    lookup with the last 2 events."""
    def __init__(self, hall_1_pin_num, hall_2_pin_num, full_motion_rotations=1):
        self.hall_1_pin_num = hall_1_pin_num
        self.hall_1_pin = Pin(hall_1_pin_num, Pin.IN, pull=Pin.PULL_UP)
        self.hall_1_pin.irq(handler=self.callback)

        self.hall_2_pin_num = hall_2_pin_num
        self.hall_2_pin = Pin(hall_2_pin_num, Pin.IN, pull=Pin.PULL_UP)
        self.hall_2_pin.irq(handler=self.callback)

        self.full_motion_rotations = full_motion_rotations
        self.rotation_count = 0
        self.movement = STOPPED
        self.events = []
        self.last_event_time = 0

    def callback(self, pin):
        self._log_data(pin)
        self.last_event_time = time.ticks_ms()
        if len(self.events) > 1:
            if self.events[-1] in TRANSITION_MAP[self.events[-2]]:
                self.movement = TRANSITION_MAP[self.events[-2]][self.events[-1]]
            else:
                print("Invalid quadrature state: {}->{}".format(self.events[-2], self.events[-1]))
            # print("{}->{} is {}".format(self.events[-2], self.events[-1], self.movement))
        self._update_rotation_count()

    def _log_data(self, pin):
        value = pin.value()
        if pin != self.hall_1_pin:
            value += 2
        self.events.append(value)
        if len(self.events) == 3:
            self.events.pop(0)

    def _update_rotation_count(self):
        self.rotation_count += 0.125 if self.movement == CW else -0.125

    def is_moving(self):
        return abs(time.ticks_diff(time.ticks_ms(), self.last_event_time)) < 1000

    def get_percent_done(self):
        return int(self.rotation_count * 100 / self.full_motion_rotations)

    def get_last_rpm(self):
        # TODO: need more data
        return 0

    def reset(self):
        self.events.clear()
        self.rotation_count = 0
        self.last_event_time = 0
        self.movement = STOPPED


class HallData:
    def __init__(self):
        self.current = None
        self.last = None

    def clear(self):
        self.__init__()


class RotationHandler:
    """Tracks when a magnet goes in range of a pair of hall effect sensors that are positioned at about 90 degrees
    apart.  Direction can be determined by looking at the timing after a full rotation.  For A->B->A if it was faster
    to go from A->B (90 degrees) than B->A (270 degrees) then we know it's CW."""
    def __init__(self, hall_1_pin_num, hall_2_pin_num, full_motion_rotations=1):
        self.hall_1_pin_num = hall_1_pin_num
        self.hall_1_pin = Pin(hall_1_pin_num, Pin.IN, pull=Pin.PULL_UP)
        self.hall_1_pin.irq(handler=self.callback, trigger=Pin.IRQ_FALLING)

        self.hall_2_pin_num = hall_2_pin_num
        self.hall_2_pin = Pin(hall_2_pin_num, Pin.IN, pull=Pin.PULL_UP)
        self.hall_2_pin.irq(handler=self.callback, trigger=Pin.IRQ_FALLING)

        self.full_motion_rotations = full_motion_rotations
        self.rotation_count = 0
        self.movement = STOPPED
        self.hall_1_data = HallData()
        self.hall_2_data = HallData()

    def callback(self, pin):
        now_ticks = time.ticks_ms()
        if pin == self.hall_1_pin:
            print("Hall 1 in range...")
            self._log_data(self.hall_1_data, now_ticks)
            self._set_movement(now_ticks, self.hall_1_data, self.hall_2_data, CCW, CW)
        else:
            print("Hall 2 in range...")
            self._log_data(self.hall_2_data, now_ticks)
            self._set_movement(now_ticks, self.hall_2_data, self.hall_1_data, CW, CCW)

        print("Movement: {}, Speed: {}, Rotations: {}, Percent: {}".format(self.movement, self.get_last_rpm(),
                                                                           self.rotation_count,
                                                                           self.get_percent_done()))

    def _set_movement(self, now, first_hall, second_hall, first_movement, second_movement):
        if first_hall.last and first_hall.current and second_hall.current:
            if time.ticks_diff(now, second_hall.current) < (
                    time.ticks_diff(now, first_hall.last) / 2):
                self.movement = first_movement
            else:
                self.movement = second_movement
            self._update_rotation_count()

    def _update_rotation_count(self):
        self.rotation_count += 0.5 if self.movement == CW else -0.5

    def is_moving(self):
        return abs(time.ticks_diff(time.ticks_ms(), self.hall_1_data.current)) < 1000

    def get_percent_done(self):
        return int(self.rotation_count * 100 / self.full_motion_rotations)

    def _log_data(self, rotation_data, now):
        rotation_data.last = rotation_data.current
        rotation_data.current = now

    def get_last_rpm(self):
        if self.hall_1_data.current and self.hall_1_data.last:
            return round(60 / abs(time.ticks_diff(self.hall_1_data.current, self.hall_1_data.last) / 1000),
                         2)

    def reset(self):
        self.hall_1_data.clear()
        self.hall_2_data.clear()
        self.rotation_count = 0
        self.movement = STOPPED
