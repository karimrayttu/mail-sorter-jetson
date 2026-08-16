"""Rotating bin control using a stepper motor and AS5600 feedback."""

import time

try:
    import RPi.GPIO as GPIO
except Exception as exc:
    GPIO = None
    GPIO_IMPORT_ERROR = exc
else:
    GPIO_IMPORT_ERROR = None

from .as5600_encoder import norm360, signed_delta_deg


class RotatingBin:
    def __init__(self, encoder, dir_pin: int, step_pin: int, cw_value: int,
                 enable_pin: int = None, enable_active_low: bool = True,
                 step_high_s: float = 0.0005, step_low_s: float = 0.0005,
                 target_margin_deg: float = 0.4, stop_early_deg: float = 0.0,
                 print_period_s: float = 0.10,
                 max_steps: int = 20000, move_timeout_s: float = 30.0):
        if GPIO is None:
            raise RuntimeError(f"RPi.GPIO is not available: {GPIO_IMPORT_ERROR}")

        self.encoder = encoder
        self.dir_pin = dir_pin
        self.step_pin = step_pin
        self.cw_value = cw_value
        self.enable_pin = enable_pin
        self.enable_active_low = enable_active_low
        self.step_high_s = step_high_s
        self.step_low_s = step_low_s
        self.target_margin_deg = target_margin_deg
        self.stop_early_deg = stop_early_deg
        self.print_period_s = print_period_s
        # Bounds that do not depend on the encoder telling the truth. A jammed
        # belt, a disabled driver, a magnet knocked off the shaft or a wedged
        # I2C read all look like "angle never changes", and the travel counter
        # below can never trip on that. These two can.
        self.max_steps = max_steps
        self.move_timeout_s = move_timeout_s
        self.cw_increases_angle = True

        GPIO.setup(self.dir_pin, GPIO.OUT, initial=self.cw_value)
        GPIO.setup(self.step_pin, GPIO.OUT, initial=GPIO.LOW)
        if self.enable_pin is not None:
            off_value = GPIO.HIGH if self.enable_active_low else GPIO.LOW
            GPIO.setup(self.enable_pin, GPIO.OUT, initial=off_value)

    def enable(self, on: bool) -> None:
        if self.enable_pin is None:
            return
        if self.enable_active_low:
            GPIO.output(self.enable_pin, GPIO.LOW if on else GPIO.HIGH)
        else:
            GPIO.output(self.enable_pin, GPIO.HIGH if on else GPIO.LOW)

    def pulse_step(self) -> None:
        GPIO.output(self.step_pin, GPIO.HIGH)
        time.sleep(self.step_high_s)
        GPIO.output(self.step_pin, GPIO.LOW)
        time.sleep(self.step_low_s)

    def sniff_direction(self) -> bool:
        """Check whether my CW pin value makes the encoder angle increase."""
        start = self.encoder.angle_deg()
        GPIO.output(self.dir_pin, self.cw_value)
        for _ in range(25):
            self.pulse_step()
        end = self.encoder.angle_deg()
        self.cw_increases_angle = signed_delta_deg(end, start) > 0.0
        return self.cw_increases_angle

    def _dir_for_delta(self, delta_deg: float) -> int:
        wants_angle_increase = delta_deg > 0.0
        if wants_angle_increase:
            return self.cw_value if self.cw_increases_angle else (1 - self.cw_value)
        return (1 - self.cw_value) if self.cw_increases_angle else self.cw_value

    def move_to_abs_deg(self, destination_deg: float) -> float:
        """Move to an absolute bin angle. Returns the final measured angle."""
        destination_deg = norm360(destination_deg)
        self.enable(True)

        current = self.encoder.angle_deg()
        delta_to_dest = signed_delta_deg(destination_deg, current)
        print(f"[BIN] current={current:7.3f} deg  dest={destination_deg:7.3f} deg  delta={delta_to_dest:7.3f} deg")

        if abs(delta_to_dest) <= self.target_margin_deg:
            print(f"[BIN] already close enough: {current:.2f} deg")
            return current

        target_deg = destination_deg
        if self.stop_early_deg > 0.0 and abs(delta_to_dest) > self.stop_early_deg + self.target_margin_deg:
            sign = 1.0 if delta_to_dest > 0 else -1.0
            target_deg = norm360(destination_deg - sign * self.stop_early_deg)

        delta_to_target = signed_delta_deg(target_deg, current)
        move_positive = delta_to_target > 0.0
        dir_value = self._dir_for_delta(delta_to_target)
        GPIO.output(self.dir_pin, dir_value)

        last_print = time.time()
        previous = current
        traveled = 0.0
        max_travel = 360.0 * 3 + 5.0
        steps = 0
        deadline = time.time() + self.move_timeout_s

        while True:
            current = self.encoder.angle_deg()
            delta = signed_delta_deg(target_deg, current)

            if time.time() - last_print >= self.print_period_s:
                print(f"[BIN] angle={current:7.3f} deg  to_go={abs(delta):7.3f} deg")
                last_print = time.time()

            if move_positive and delta <= -self.target_margin_deg:
                break
            if (not move_positive) and delta >= self.target_margin_deg:
                break

            traveled += abs(signed_delta_deg(current, previous))
            previous = current
            if traveled > max_travel:
                print("[WARN] bin moved farther than expected; stopping")
                break

            # traveled only grows when the encoder says the shaft moved, so it
            # cannot catch a shaft that is not moving at all. Step count and
            # wall clock are measured on this side of the encoder and do.
            if steps >= self.max_steps:
                print(f"[WARN] {steps} steps with no arrival; stopping. "
                      "Check the driver enable, the belt and the shaft magnet.")
                break
            if time.time() > deadline:
                print(f"[WARN] move exceeded {self.move_timeout_s:.0f} s; stopping. "
                      "Check the driver enable, the belt and the shaft magnet.")
                break

            self.pulse_step()
            steps += 1

        final_angle = self.encoder.angle_deg()
        print(f"[BIN HIT] target={target_deg:.1f} deg  final={final_angle:.2f} deg")
        return final_angle
