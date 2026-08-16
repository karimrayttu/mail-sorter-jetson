"""Check that the two bin maps still agree.

    python tools/check_bin_maps.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from config import BIN_SLOTS  # noqa: E402


def parse_encoder_map() -> dict[str, float]:
    """Read CITY_TO_ANGLE out of rotbin_encoder.py without importing it."""
    source = (REPO / "src" / "hardware" / "rotbin_encoder.py").read_text(encoding="utf-8")
    block = re.search(r"CITY_TO_ANGLE\s*=\s*\{(.*?)\}", source, re.DOTALL)
    if not block:
        raise SystemExit("could not find CITY_TO_ANGLE in rotbin_encoder.py")
    return {name.lower(): float(angle)
            for name, angle in re.findall(r"[\"']([^\"']+)[\"']\s*:\s*([0-9.]+)",
                                          block.group(1))}


def main() -> int:
    config_map = {name.lower(): float(angle) for name, angle in BIN_SLOTS.items()}
    encoder_map = parse_encoder_map()
    problems = []

    for city in sorted(set(config_map) | set(encoder_map)):
        in_config = config_map.get(city)
        in_encoder = encoder_map.get(city)
        if in_config is None:
            problems.append(f"{city}: missing from config.BIN_SLOTS")
        elif in_encoder is None:
            problems.append(f"{city}: missing from rotbin_encoder.CITY_TO_ANGLE")
        elif abs(in_config - in_encoder) > 1e-6:
            problems.append(f"{city}: {in_config}° in config, {in_encoder}° in encoder")

    if problems:
        print("BIN MAPS DISAGREE")
        for problem in problems:
            print(" -", problem)
        return 1

    print(f"bin maps agree on all {len(config_map)} slots")
    for city, angle in sorted(config_map.items(), key=lambda kv: kv[1]):
        print(f"  {city:<12} {angle:6.1f}°")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
