#!/usr/bin/env python3
"""Rotating bin controller with AS5600 encoder and stepper driver."""

import time
import math
import json
import os
import sys

try:                        # what the Jetson ships
    import smbus2 as smbus
except ImportError:         # older Pi-style package
    import smbus            # type: ignore[no-redef]

try:                        # NVIDIA's package, not on pip
    import Jetson.GPIO as GPIO
except ImportError:         # same API on a Raspberry Pi
    import RPi.GPIO as GPIO  # type: ignore[no-redef]

# ================== USER SETTINGS ==================
DIR = 20
STEP = 21
CW = 0

USE_ENABLE = True
ENABLE_PIN = 16
ENABLE_ACTIVE_LOW = True

STEP_HIGH_S_CRUISE = 0.0005
STEP_LOW_S_CRUISE  = 0.0005

APPROACH_WINDOW_DEG   = 10.0
STEP_HIGH_S_APPROACH  = 0.0012
STEP_LOW_S_APPROACH   = 0.0012

CREEP_WINDOW_DEG    = 2.0
STEP_HIGH_S_CREEP   = 0.0020
STEP_LOW_S_CREEP    = 0.0020

PAUSE_S          = 5.0
PRINT_PERIOD_S   = 0.1
TARGET_MARGIN_DEG = 0.4

# Stop 5 degrees before target so motor ends smooth
LEAD_DEG = 5.0

# ===================================================
# =============== CITY / BIN MAPPING ================
# 6 equal sectors of 60° each. Adjust angles if your
# physical bin order is different.
CITY_TO_ANGLE = {
    "lubbock":      0.0,   # Bin 1
    "san antonio": 60.0,   # Bin 2
    "houston":    120.0,   # Bin 3
    "austin":     180.0,   # Bin 4
    "dallas":     240.0,   # Bin 5
    "unknown":    300.0,   # Bin 6 (reject / overflow)
}
CITY_NAMES_STR = ", ".join(n.capitalize() for n in CITY_TO_ANGLE.keys())

def city_for_angle(deg: float) -> str:
    """
    Decode which sector a given angle is in, for debug / calibration.
    """
    d = deg % 360.0
    if   0   <= d <  60:  return "Lubbock"
    elif 60  <= d < 120:  return "San Antonio"
    elif 120 <= d < 180:  return "Houston"
    elif 180 <= d < 240:  return "Austin"
    elif 240 <= d < 300:  return "Dallas"
    else:                 return "Unknown"

def route_city(city_name: str):
    """    External entrypoint: rotate bin to specific city and BLOCK until fully done."""
    if not city_name:
        city_key = "unknown"
    else:
        city_key = city_name.strip().lower()

    if city_key not in CITY_TO_ANGLE:
        print(f"[BIN] Unknown city '{city_name}', routing to UNKNOWN bin.")
        city_key = "unknown"

    target_deg = CITY_TO_ANGLE[city_key]
    print(f"[BIN] Routing to {city_key.capitalize()} → {target_deg:.1f}°")
    move_to_absolute_angle(target_deg)
    print("[BIN] Rotation complete.")

# ================== ANGLE / ENCODER HELPERS ==================
def norm360(d: float) -> float:
    return d % 360.0

def signed_delta_deg(a1: float, a0: float) -> float:
    """
    Shortest signed delta a1-a0 in [-180, 180).
    """
    return ((a1 - a0 + 540.0) % 360.0) - 180.0

def plan_stop_unwrapped(curr_unwrapped: float,
                        target_deg: float,
                        lead_deg: float,
                        expect_cw: bool) -> float:
    """
    Choose unwrapped stop threshold for new command so we don't "hit" immediately.
    """
    stop_base = (target_deg - lead_deg) % 360.0
    if expect_cw:
        n = math.floor((curr_unwrapped - stop_base) / 360.0) + 1
    else:
        n = math.floor((curr_unwrapped - stop_base) / 360.0)
    return stop_base + 360.0 * n

# ================== CALIBRATION ==================
def cal_file_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "rotbin_cal.json")

def load_cal_zero_raw(default: int) -> int:
    try:
        with open(cal_file_path(), "r") as f:
            data = json.load(f)
        return int(data["cal_zero_raw"]) & 0x0FFF
    except Exception:
        return default & 0x0FFF

def save_cal_zero_raw(v: int) -> None:
    try:
        with open(cal_file_path(), "w") as f:
            json.dump({"cal_zero_raw": int(v) & 0x0FFF}, f, indent=2)
        print(f"[CAL] Saved cal_zero_raw={v & 0x0FFF}")
    except Exception as e:
        print(f"[CAL] Save error: {e}")

# ================== AS5600 ==================
AS5600_ADDR   = 0x36
REG_ANGLE_MSB = 0x0E
REG_ANGLE_LSB = 0x0F
CPR           = 4096
DEG_PER_COUNT = 360.0 / CPR

# Opened by setup_hardware(). Left as None so that importing this module does
# not touch the I2C bus.
bus = None

def read_angle_raw12_once() -> int:
    if bus is None:
        raise RuntimeError("call setup_hardware() before reading the encoder")
    bus.write_byte(AS5600_ADDR, REG_ANGLE_MSB)
    msb = bus.read_byte(AS5600_ADDR) & 0x0F
    bus.write_byte(AS5600_ADDR, REG_ANGLE_LSB)
    lsb = bus.read_byte(AS5600_ADDR)
    return ((msb << 8) | lsb) & 0x0FFF

def read_angle_raw12_median(n: int = 5) -> int:
    vals = []
    for _ in range(n):
        vals.append(read_angle_raw12_once())
        time.sleep(0.0002)
    vals.sort()
    return vals[n // 2]

def rel_counts(now: int, zero: int) -> int:
    return (now - zero) & 0x0FFF

def counts_to_deg(c: int) -> float:
    return c * DEG_PER_COUNT

prev_wrapped = 0.0
turns = 0
unwrapped = 0.0
expect_cw = True
zero_raw = 0
_ready = False

def pulse_step(H: float, L: float) -> None:
    GPIO.output(STEP, GPIO.HIGH)
    time.sleep(H)
    GPIO.output(STEP, GPIO.LOW)
    time.sleep(L)

def motor_enable(on: bool) -> None:
    if not USE_ENABLE:
        return
    GPIO.output(
        ENABLE_PIN,
        GPIO.LOW if (on and ENABLE_ACTIVE_LOW) else GPIO.HIGH
    )

# ================== STARTUP ==================
def setup_hardware() -> None:
    """Open I2C, claim the GPIO pins, and work out which way the shaft turns."""
    global bus, zero_raw, expect_cw, prev_wrapped, turns, unwrapped, _ready
    if _ready:
        return

    bus = smbus.SMBus(1)

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(DIR, GPIO.OUT, initial=CW)
    GPIO.setup(STEP, GPIO.OUT, initial=GPIO.LOW)
    if USE_ENABLE:
        GPIO.setup(ENABLE_PIN, GPIO.OUT,
                   initial=(GPIO.LOW if ENABLE_ACTIVE_LOW else GPIO.HIGH))
        GPIO.output(ENABLE_PIN, GPIO.LOW if ENABLE_ACTIVE_LOW else GPIO.HIGH)

    time.sleep(0.2)
    startup_raw = read_angle_raw12_median()
    zero_raw    = load_cal_zero_raw(startup_raw)
    print(f"[INFO] Startup raw={startup_raw}, cal_zero_raw={zero_raw}")

    # Detect direction (CW or CCW). This is the one place that moves the shaft
    # without being asked to: 25 pulses, well under one bin width.
    a0 = counts_to_deg(rel_counts(read_angle_raw12_median(), zero_raw))
    for _ in range(25):
        pulse_step(0.0008, 0.0008)
    a1 = counts_to_deg(rel_counts(read_angle_raw12_median(), zero_raw))
    expect_cw = signed_delta_deg(a1, a0) > 0
    print(f"[INFO] expect_cw={expect_cw}")

    prev_wrapped = a1
    turns = 0
    unwrapped = a1
    _ready = True

def get_wrapped_deg() -> float:
    raw = read_angle_raw12_median()
    cnt = rel_counts(raw, zero_raw)
    return counts_to_deg(cnt)

def unwrap(prev: float, curr: float, turns_in: int, cw: bool):
    turns_local = turns_in
    if cw:
        if curr < prev - 180.0:
            turns_local += 1
    else:
        if curr > prev + 180.0:
            turns_local -= 1
    return turns_local, curr + 360.0 * turns_local

def get_unwrapped_deg():
    global prev_wrapped, unwrapped, turns
    w = get_wrapped_deg()
    turns, unwrapped = unwrap(prev_wrapped, w, turns, expect_cw)
    prev_wrapped = w
    return w, unwrapped

def rebase_unwrap_after_zero_change():
    global prev_wrapped, turns, unwrapped
    w = get_wrapped_deg()
    prev_wrapped = w
    turns = 0
    unwrapped = w

# ================== MAIN MOVE FUNCTION ==================
def move_to_absolute_angle(target_deg: float) -> None:
    """
    Move to target_deg (0–360). BLOCKS until stopping + PAUSE_S are complete.
    """
    global prev_wrapped, unwrapped, turns

    setup_hardware()
    motor_enable(True)

    # Initial unwrap update
    w = get_wrapped_deg()
    turns, unwrapped = unwrap(prev_wrapped, w, turns, expect_cw)
    prev_wrapped = w

    target_deg = norm360(target_deg)
    stop_unwrapped = plan_stop_unwrapped(unwrapped, target_deg, LEAD_DEG, expect_cw)

    print(f"[CMD] Move to {target_deg:.1f}° (stop@ {(stop_unwrapped % 360.0):.1f}°)")

    last_print = 0.0
    while True:
        w = get_wrapped_deg()
        turns, unwrapped = unwrap(prev_wrapped, w, turns, expect_cw)
        prev_wrapped = w

        delta = (stop_unwrapped - unwrapped) if expect_cw else (unwrapped - stop_unwrapped)

        if delta <= CREEP_WINDOW_DEG:
            pulse_step(STEP_HIGH_S_CREEP, STEP_LOW_S_CREEP)
        elif delta <= APPROACH_WINDOW_DEG:
            pulse_step(STEP_HIGH_S_APPROACH, STEP_LOW_S_APPROACH)
        else:
            pulse_step(STEP_HIGH_S_CRUISE, STEP_LOW_S_CRUISE)

        now = time.time()
        if now - last_print >= PRINT_PERIOD_S:
            print(f"Angle={w:7.3f}°  Unwrapped={unwrapped:7.3f}°  Stop={(stop_unwrapped % 360.0):6.1f}°")
            last_print = now

        if expect_cw:
            hit = unwrapped >= (stop_unwrapped + TARGET_MARGIN_DEG)
        else:
            hit = unwrapped <= (stop_unwrapped - TARGET_MARGIN_DEG)

        if hit:
            print(f"[HIT] Stopping at {(stop_unwrapped % 360.0):.1f}°, pausing {PAUSE_S:.1f}s...")
            time.sleep(PAUSE_S)
            break

    motor_enable(False)

# ================== OPTIONAL CLI ==================
def interactive_loop():
    print("Cities:", CITY_NAMES_STR)
    print("Type a city name (or 'unknown') or an angle.")
    while True:
        try:
            s = input("Cmd> ").strip()
            if s.lower() in ("q", "quit", "exit"):
                break
            if s.lower() in CITY_TO_ANGLE:
                route_city(s)
                continue
            ang = float(s)
            move_to_absolute_angle(norm360(ang))
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    setup_hardware()
    if len(sys.argv) > 1:
        route_city(" ".join(sys.argv[1:]))
    else:
        interactive_loop()
