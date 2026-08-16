"""Mail sorter settings.

I kept the wiring and tuning values in one place because these changed a lot while testing the sorter.
"""

# ---------------- Conveyor stepper ----------------
DIR_CONV = 6
STEP_CONV = 13
CW_CONV = 1
STEP_DELAY_S = 0.001

# ---------------- Breakbeam ----------------
BEAM_PIN = 17
BEAM_INVERT_LOGIC = False
BEAM_BOUNCE_S = 0.01

# ---------------- Rotating bin stepper ----------------
DIR_BIN = 20
STEP_BIN = 21
CW_BIN = 0              # My wiring used logic 0 as clockwise
USE_ENABLE = True
ENABLE_PIN = 16
ENABLE_ACTIVE_LOW = True

BIN_STEP_HIGH_S = 0.0005
BIN_STEP_LOW_S = 0.0005
TARGET_MARGIN_DEG = 0.4
STOP_EARLY_DEG = 5.0
PRINT_PERIOD_S = 0.10

# ---------------- AS5600 encoder ----------------
AS5600_ADDR = 0x36
AS5600_REG_ANGLE_MSB = 0x0E
AS5600_REG_ANGLE_LSB = 0x0F
AS5600_CPR = 4096
AS5600_MEDIAN_N = 5
ZERO_FILE = "as5600_zero.txt"

# ---------------- Sorting bins ----------------
# These match the final six-slot rotating bin layout.
BIN_SLOTS = {
    "Lubbock": 0.0,
    "San Antonio": 60.0,
    "Houston": 120.0,
    "Austin": 180.0,
    "Dallas": 240.0,
    "Unknown": 300.0,
}

ALLOWED_CITIES = {"Houston", "San Antonio", "Dallas", "Austin", "Lubbock"}
