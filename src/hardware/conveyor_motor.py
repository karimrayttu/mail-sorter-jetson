"""Conveyor stepper control.

This is intentionally basic: one step pulse at a time. It was easier to tune on the bench and
it kept the conveyor behavior predictable while I was working on the vision side.
"""

import time

try:
    import RPi.GPIO as GPIO
except Exception as exc:
    GPIO = None
    GPIO_IMPORT_ERROR = exc
else:
    GPIO_IMPORT_ERROR = None


class ConveyorMotor:
    def __init__(self, dir_pin: int, step_pin: int, cw_value: int = 1, step_delay_s: float = 0.001):
        if GPIO is None:
            raise RuntimeError(f"RPi.GPIO is not available: {GPIO_IMPORT_ERROR}")

        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.step_delay_s = step_delay_s

        GPIO.setup(self.dir_pin, GPIO.OUT, initial=cw_value)
        GPIO.setup(self.step_pin, GPIO.OUT, initial=GPIO.LOW)

    def step_once(self) -> None:
        GPIO.output(self.step_pin, GPIO.HIGH)
        time.sleep(self.step_delay_s)
        GPIO.output(self.step_pin, GPIO.LOW)
        time.sleep(self.step_delay_s)

    def run_for_steps(self, steps: int) -> None:
        for _ in range(max(0, steps)):
            self.step_once()
