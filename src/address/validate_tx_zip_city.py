#!/usr/bin/env python3
"""Quick checker for the ZIP/city CSV used by the address verifier."""

import csv
import json
import re
import sys
from collections import Counter

ALLOWED = {"Houston", "San Antonio", "Dallas", "Austin", "Lubbock"}


def main(path: str) -> None:
    seen = set()
    per_city = Counter()
    errors = []

    with open(path, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            # Reset per row. Without this a row that takes the "both a ZIP and a
            # prefix" branch below never assigns key, which is an
            # UnboundLocalError on the first row and a phantom duplicate report
            # against the previous row's key on any later one.
            key = None
            zip5 = (row.get("zip") or "").strip()
            zip_prefix = (row.get("zip_prefix") or "").strip()
            city = (row.get("city") or "").strip().title()

            if city not in ALLOWED:
                errors.append(f"line {line_no}: city {city!r} is not in the allowed list")

            # A row carries either a full 5-digit ZIP or a 3-digit prefix, matching
            # what load_zip_csv() in address_verify.py accepts.
            if zip5 and zip_prefix:
                errors.append(f"line {line_no}: row has both a ZIP and a prefix")
            elif zip5:
                if not re.fullmatch(r"\d{5}", zip5):
                    errors.append(f"line {line_no}: ZIP {zip5!r} is not 5 digits")
                key = ("zip", zip5)
            elif zip_prefix:
                if not re.fullmatch(r"\d{3}", zip_prefix):
                    errors.append(f"line {line_no}: prefix {zip_prefix!r} is not 3 digits")
                key = ("prefix", zip_prefix)
            else:
                errors.append(f"line {line_no}: row has neither a ZIP nor a prefix")
                key = None

            if key and key in seen:
                errors.append(f"line {line_no}: duplicate {key[0]} {key[1]!r}")
            if key:
                seen.add(key)
            per_city[city] += 1

    if errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(" -", error)
        raise SystemExit(1)

    print("VALIDATION OK")
    print(json.dumps(per_city, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_tx_zip_city.py data/tx_zip_city.csv")
        raise SystemExit(2)
    main(sys.argv[1])
