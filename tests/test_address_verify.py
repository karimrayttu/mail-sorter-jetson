"""Behaviour tests for the address matcher and the bin map.

    python tests/test_address_verify.py
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from address.address_verify import (  # noqa: E402
    FUZZY_MIN_SCORE,
    ALLOWED,
    HAVE_RAPIDFUZZ,
    fuzzy_city,
    load_zip_csv,
    parse_zip5s_loose,
    verify_address,
)
from config import BIN_SLOTS  # noqa: E402

assert HAVE_RAPIDFUZZ, (
    "rapidfuzz is missing, so the fuzzy stage is degraded and the fuzzy tests "
    "below cannot mean anything. pip install -r requirements.txt")

ZIP_CSV = os.path.join(REPO, "data", "tx_zip_city.example.csv")


class ZipParsing(unittest.TestCase):
    def test_plain_zip_is_found(self):
        self.assertEqual(parse_zip5s_loose("HOUSTON, TX 77002"), ["77002"])

    def test_ocr_letter_digit_confusion_is_undone(self):
        # O for 0, I for 1, S between digits for 5: the swaps EasyOCR actually made.
        self.assertIn("77002", parse_zip5s_loose("HOUSTON, TX 77OO2"))
        self.assertIn("78701", parse_zip5s_loose("AUSTIN, TX 787OI"))

    def test_zip_plus_four_reduces_to_five(self):
        self.assertEqual(parse_zip5s_loose("DALLAS, TX 75202-1234"), ["75202"])


class Resolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = load_zip_csv(ZIP_CSV)

    def resolve(self, *lines):
        return verify_address(list(lines), self.index)

    def test_exact_zip_wins(self):
        result = self.resolve("GULF COAST SUPPLY CO", "1200 MAIN ST", "HOUSTON, TX 77002")
        self.assertEqual(result["city"], "Houston")
        self.assertEqual(result["method"], "zip")

    def test_prefix_zip_resolves_when_the_exact_code_is_unknown(self):
        result = self.resolve("SOME COMPANY", "1 NOWHERE RD", "TX 79499")
        self.assertEqual(result["city"], "Lubbock")
        self.assertEqual(result["method"], "zip")

    def test_city_state_line_carries_it_without_a_zip(self):
        result = self.resolve("TRINITY LOGISTICS LLC", "400 ELM ST", "DALLAS, TX")
        self.assertEqual(result["city"], "Dallas")
        self.assertEqual(result["method"], "city_state_line")

    def test_known_misspelling_falls_through_to_fuzzy(self):
        result = self.resolve("SOME CO", "1 MAIN", "houstin tx")
        self.assertEqual(result["city"], "Houston")
        self.assertEqual(result["method"], "fuzzy")

    def test_empty_input_is_unknown(self):
        result = self.resolve("")
        self.assertEqual(result["city"], "unknown")
        self.assertEqual(result["confidence"], 0.0)

    def test_every_allowed_city_has_a_bin(self):
        slots = {name.lower() for name in BIN_SLOTS}
        for city in ALLOWED:
            self.assertIn(city.lower(), slots, f"{city} has no bin slot")
        self.assertIn("unknown", slots, "there must be a reject bin")


class MisrouteRegression(unittest.TestCase):
    """Garbled OCR must reject, never name a city."""

    GARBAGE = [
        ("San Antonio", "AlAMO aaty Olot M iaoemooar Aaaana toren"),
        ("Austin", "ColorAdo MVCR TAnino csEohoatasAyt uore Hdt"),
    ]

    @classmethod
    def setUpClass(cls):
        cls.index = load_zip_csv(ZIP_CSV)

    def test_garbled_text_goes_to_the_unknown_bin(self):
        for truth, text in self.GARBAGE:
            with self.subTest(truth=truth):
                result = verify_address([text], self.index)
                self.assertEqual(
                    result["city"], "unknown",
                    f"garbled {truth} label resolved to {result['city']!r}; "
                    "a misroute is worse than a reject")

    def test_the_floor_sits_above_the_garbage_band(self):
        for _, text in self.GARBAGE:
            _, score = fuzzy_city([text])
            self.assertLess(score, FUZZY_MIN_SCORE)

    def test_a_shared_prefix_is_not_a_city_match(self):
        """`san` alone must not carry an address into the San Antonio bin."""
        index = load_zip_csv(ZIP_CSV)
        for text in ("SAN FRANCISCO CA", "SAN DIEGO, CA 92101",
                     "SAN JOSE CA 95113"):
            with self.subTest(text=text):
                self.assertEqual(verify_address([text], index)["city"], "unknown")
                _, score = fuzzy_city([text])
                self.assertLess(score, FUZZY_MIN_SCORE)

    def test_the_floor_sits_below_genuine_misspellings(self):
        for text in ("HOUSTONN TX", "AUSTN TX", "DALAS TX", "LUBOCK TX",
                     "SAN ANTONIQ TX", "HOUSTQN"):
            with self.subTest(text=text):
                _, score = fuzzy_city([text])
                self.assertGreaterEqual(score, FUZZY_MIN_SCORE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
