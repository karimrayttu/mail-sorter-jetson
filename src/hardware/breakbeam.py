"""IR breakbeam helper for the sorter.

The sensor is only used as a gate: when the beam is broken, the conveyor stops and the
sort decision can happen without the mail moving past the camera.
"""

try:
    from gpiozero import Button
except Exception as exc:  # keeps imports readable on non-Jetson machines
    Button = None
    GPIO_IMPORT_ERROR = exc
else:
    GPIO_IMPORT_ERROR = None


class Breakbeam:
    def __init__(self, pin: int, invert_logic: bool = False, bounce_time: float = 0.01):
        if Button is None:
            raise RuntimeError(f"gpiozero is not available: {GPIO_IMPORT_ERROR}")

        self.invert_logic = invert_logic
        self.button = Button(pin, pull_up=True, bounce_time=bounce_time)

    def broken(self) -> bool:
        # With the wiring I used, not pressed meant the beam was blocked.
        return self.button.is_pressed if self.invert_logic else not self.button.is_pressed

    def ok(self) -> bool:
        return not self.broken()
