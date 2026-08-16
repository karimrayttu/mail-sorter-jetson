#!/usr/bin/env python3
"""Main hardware loop for the mail sorter.

This version keeps the routing decision manual. During testing, that made it easier to prove the
conveyor, breakbeam, encoder, and rotating bin before tying in the camera pipeline.
"""

import os
import sys

try:
    import RPi.GPIO as GPIO
except Exception as exc:
    GPIO = None
    GPIO_IMPORT_ERROR = exc
else:
    GPIO_IMPORT_ERROR = None

from config import (
    AS5600_ADDR,
    AS5600_CPR,
    AS5600_MEDIAN_N,
    AS5600_REG_ANGLE_LSB,
    AS5600_REG_ANGLE_MSB,
    BEAM_BOUNCE_S,
    BEAM_INVERT_LOGIC,
    BEAM_PIN,
    BIN_SLOTS,
    BIN_STEP_HIGH_S,
    BIN_STEP_LOW_S,
    CW_BIN,
    CW_CONV,
    DIR_BIN,
    DIR_CONV,
    ENABLE_ACTIVE_LOW,
    ENABLE_PIN,
    PRINT_PERIOD_S,
    STEP_BIN,
    STEP_CONV,
    STEP_DELAY_S,
    STOP_EARLY_DEG,
    TARGET_MARGIN_DEG,
    USE_ENABLE,
    ZERO_FILE,
)
from hardware.as5600_encoder import AS5600Encoder, norm360
from hardware.breakbeam import Breakbeam
from hardware.conveyor_motor import ConveyorMotor
from hardware.rotating_bin import RotatingBin


def choose_bin():
    while True:
        print("\n=== Select destination bin ===")
        for city, angle in BIN_SLOTS.items():
            print(f" - {city:10s} at {int(angle)} deg")
        print(" - zero       recalibrate current bin position as 0 deg")
        print(" - quit       exit")

        choice = input("Destination: ").strip()
        if not choice:
            continue
        if choice.lower() in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if choice.lower() == "zero":
            return "zero", None

        for city, angle in BIN_SLOTS.items():
            if choice.lower() == city.lower():
                return city, angle
        print("Unknown bin. Try one of the listed cities.")


def main() -> None:
    if GPIO is None:
        raise RuntimeError(f"RPi.GPIO is not available: {GPIO_IMPORT_ERROR}")

    GPIO.setmode(GPIO.BCM)

    encoder = AS5600Encoder(
        bus_id=1,
        address=AS5600_ADDR,
        reg_msb=AS5600_REG_ANGLE_MSB,
        reg_lsb=AS5600_REG_ANGLE_LSB,
        cpr=AS5600_CPR,
        median_n=AS5600_MEDIAN_N,
        zero_file=ZERO_FILE,
    )

    loaded_zero = encoder.load_zero()
    if loaded_zero is None:
        print("[ZERO] No saved zero. Setting current position as 0 deg.")
        encoder.set_zero_to_current()
    else:
        print(f"[ZERO] Loaded saved zero_raw={loaded_zero}")

    conveyor = ConveyorMotor(DIR_CONV, STEP_CONV, cw_value=CW_CONV, step_delay_s=STEP_DELAY_S)
    beam = Breakbeam(BEAM_PIN, invert_logic=BEAM_INVERT_LOGIC, bounce_time=BEAM_BOUNCE_S)
    bin_motor = RotatingBin(
        encoder=encoder,
        dir_pin=DIR_BIN,
        step_pin=STEP_BIN,
        cw_value=CW_BIN,
        enable_pin=ENABLE_PIN if USE_ENABLE else None,
        enable_active_low=ENABLE_ACTIVE_LOW,
        step_high_s=BIN_STEP_HIGH_S,
        step_low_s=BIN_STEP_LOW_S,
        target_margin_deg=TARGET_MARGIN_DEG,
        stop_early_deg=STOP_EARLY_DEG,
        print_period_s=PRINT_PERIOD_S,
    )

    bin_motor.enable(True)
    cw_increases = bin_motor.sniff_direction()
    print("[INFO] CW_BIN makes angle", "increase" if cw_increases else "decrease")

    armed = beam.ok()
    print("Sorter ready. Press Ctrl+C to exit.")

    try:
        while True:
            if armed and beam.broken():
                armed = False
                print("\n[BEAM] broken. Conveyor paused.")

                while True:
                    city, angle = choose_bin()
                    if city == "zero":
                        raw = encoder.set_zero_to_current()
                        print(f"[ZERO] saved zero_raw={raw}")
                        continue
                    print(f"[ROUTE] {city} -> {int(norm360(angle))} deg")
                    bin_motor.move_to_abs_deg(angle)
                    break

            if beam.ok():
                if not armed:
                    print("[BEAM] clear. Re-armed.")
                armed = True

            conveyor.step_once()

    except KeyboardInterrupt:
        print("\n[ABORT] stopped by user")
    finally:
        try:
            bin_motor.enable(False)
        finally:
            GPIO.cleanup()
            print("[CLEANUP] GPIO released")


if __name__ == "__main__":
    main()
