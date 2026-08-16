"""AS5600 magnetic encoder reader for the rotating bin."""

import os
import time
from typing import Optional

try:
    import smbus
except Exception:
    try:
        import smbus2 as smbus
    except Exception as exc:
        smbus = None
        SMBUS_IMPORT_ERROR = exc
    else:
        SMBUS_IMPORT_ERROR = None
else:
    SMBUS_IMPORT_ERROR = None


def norm360(deg: float) -> float:
    return deg % 360.0


def signed_delta_deg(a1: float, a0: float) -> float:
    """Shortest signed delta a1 - a0 in degrees."""
    return ((a1 - a0 + 540.0) % 360.0) - 180.0


class AS5600Encoder:
    def __init__(self, bus_id: int, address: int, reg_msb: int, reg_lsb: int,
                 cpr: int = 4096, median_n: int = 5, zero_file: str = "as5600_zero.txt"):
        if smbus is None:
            raise RuntimeError(f"smbus is not available: {SMBUS_IMPORT_ERROR}")

        self.bus = smbus.SMBus(bus_id)
        self.address = address
        self.reg_msb = reg_msb
        self.reg_lsb = reg_lsb
        self.cpr = cpr
        self.deg_per_count = 360.0 / float(cpr)
        self.median_n = median_n
        self.zero_file = zero_file
        self.zero_raw = 0

    def read_raw_once(self) -> int:
        self.bus.write_byte(self.address, self.reg_msb)
        msb = self.bus.read_byte(self.address) & 0x0F
        self.bus.write_byte(self.address, self.reg_lsb)
        lsb = self.bus.read_byte(self.address)
        return ((msb << 8) | lsb) & 0x0FFF

    def read_raw_median(self) -> int:
        vals = []
        n = max(1, self.median_n)
        for _ in range(n):
            vals.append(self.read_raw_once())
            time.sleep(0.0002)
        vals.sort()
        return vals[n // 2]

    def load_zero(self) -> Optional[int]:
        if not os.path.exists(self.zero_file):
            return None
        try:
            with open(self.zero_file, "r", encoding="utf-8") as f:
                value = int(f.read().strip())
            if 0 <= value < self.cpr:
                self.zero_raw = value
                return value
        except Exception:
            return None
        return None

    def save_zero(self, raw_value: int) -> None:
        with open(self.zero_file, "w", encoding="utf-8") as f:
            f.write(f"{int(raw_value)}\n")

    def set_zero_to_current(self) -> int:
        self.zero_raw = self.read_raw_median()
        self.save_zero(self.zero_raw)
        return self.zero_raw

    def angle_deg(self) -> float:
        raw = self.read_raw_median()
        rel_counts = (raw - self.zero_raw) & 0x0FFF
        return norm360(rel_counts * self.deg_per_count)
