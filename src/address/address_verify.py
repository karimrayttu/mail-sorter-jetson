#!/usr/bin/env python3
"""Clean OCR address text and pick the most likely allowed destination city."""

import csv
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Set

# rapidfuzz is a hard requirement for the fuzzy stage and is listed in
# requirements.txt. Without it the ZIP and city-state stages still work, but
# fuzzy_city() degrades to the hand-written ALIASES table below and scores 0.0
# on anything not spelled exactly like an entry in it. HAVE_RAPIDFUZZ is
# exported so callers and tests can tell the two states apart.
try:
    from rapidfuzz import fuzz, process as rfproc
except Exception:
    fuzz = None
    rfproc = None

HAVE_RAPIDFUZZ = rfproc is not None

ALLOWED = {"Houston", "San Antonio", "Dallas", "Austin", "Lubbock"}

# The fuzzy stage will not name a city below this score; the piece goes to the
# unknown bin instead. Measured with `python tools/pipeline_bench.py
# --per-condition 4` against real EasyOCR output: genuine misspellings score
# 0.857 to 1.000, while the garbled text off the worst captures scores 0.500 to
# 0.727. Without a floor the matcher answered "Dallas" for a San Antonio
# envelope at 0.545, which puts mail on a truck to the wrong city. A reject
# costs one manual re-run, so the floor sits above the garbage band.
FUZZY_MIN_SCORE = 0.80

ALIASES = {
    "houston": ["houston", "houstin", "huston", "hoston", "houstom", "houstn"],
    "san antonio": ["san antonio", "sanantonio", "san ant", "sn antonio", "san antono"],
    "dallas": ["dallas", "dailas", "dal las", "dllas", "dalas"],
    "austin": ["austin", "aus tin", "aust1n", "aistin", "autin", "ostin"],
    "lubbock": ["lubbock", "lubock", "lubbok", "lubbuck", "lubbosk"],
}


def norm(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    return re.sub(r"\s{2,}", " ", text)


def parse_zip5s_loose(text: str) -> List[str]:
    # OCR likes turning O/I/S into digits in ZIP codes. This catches the common ones.
    cleaned = text.replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1")
    cleaned = re.sub(r"(?<=\d)[Ss](?=\d)", "5", cleaned)
    candidates = re.findall(r"\b\d{5}(?:[ \-]?\d[ \-]?\d[ \-]?\d[ \-]?\d)?\b", cleaned)

    zips = []
    seen = set()
    for candidate in candidates:
        zip5 = re.sub(r"\D", "", candidate)[:5]
        if len(zip5) == 5 and zip5 not in seen:
            zips.append(zip5)
            seen.add(zip5)
    return zips


def load_zip_csv(path: str) -> Dict[str, Dict[str, Set[str]]]:
    exact = {}
    prefix = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            zip5 = (row.get("zip") or "").strip()
            zip_prefix = (row.get("zip_prefix") or "").strip()
            city = (row.get("city") or "").strip().title()
            if city not in ALLOWED:
                continue
            if re.fullmatch(r"\d{5}", zip5):
                exact.setdefault(zip5, set()).add(city)
            elif re.fullmatch(r"\d{3}", zip_prefix):
                prefix.setdefault(zip_prefix, set()).add(city)
    return {"exact": exact, "prefix": prefix}


def city_from_zip(zip5: str, zip_index) -> Set[str]:
    if not zip5:
        return set()
    if zip5 in zip_index.get("exact", {}):
        return zip_index["exact"][zip5] & ALLOWED
    return zip_index.get("prefix", {}).get(zip5[:3], set()) & ALLOWED


def extract_city_state(lines: Iterable[str]) -> str:
    joined = " | ".join(lines)
    match = re.search(r"([A-Za-z][A-Za-z\s\-]{2,}?)\s*,\s*TX\b", joined, re.IGNORECASE)
    if not match:
        return ""
    city = match.group(1).strip().title()
    return city if city in ALLOWED else ""


def undigit(token: str) -> str:
    """Undo the digit-for-letter swaps OCR makes inside words."""
    return token.translate(str.maketrans("015", "ois"))


def candidate_phrases(line: str) -> List[str]:
    """Single words plus adjacent word pairs, so `san antonio` can be matched."""
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", norm(line)) if re.search(r"[a-z]", t)]
    phrases = list(tokens)
    phrases += [undigit(t) for t in tokens if re.search(r"\d", t)]
    phrases += [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
    return phrases


def fuzzy_city(lines: Iterable[str]) -> tuple[str, float]:
    """Best city score over every word and word pair in the text."""
    allowed_lower = [c.lower() for c in ALLOWED]
    scores = defaultdict(float)
    for line in lines:
        for phrase in candidate_phrases(line):
            for canon, aliases in ALIASES.items():
                if phrase in aliases or canon.replace(" ", "") == phrase:
                    scores[canon.title()] = max(scores[canon.title()], 1.0)
            if rfproc is not None:
                candidate, score, _ = rfproc.extractOne(
                    phrase, allowed_lower, scorer=fuzz.ratio)
                for allowed in ALLOWED:
                    if allowed.lower() == candidate:
                        scores[allowed] = max(scores[allowed], score / 100.0)
    if not scores:
        return "", 0.0
    city, score = sorted(scores.items(), key=lambda item: item[1], reverse=True)[0]
    return city, float(score)


def verify_address(ocr_lines: List[str], zip_index=None) -> dict:
    lines = [re.sub(r"\s{2,}", " ", line.strip()) for line in ocr_lines if line and line.strip()]
    blob = " ".join(lines)
    reasons = []

    if zip_index is None:
        zip_index = {"exact": {}, "prefix": {}}

    zips = parse_zip5s_loose(blob)
    reasons.append(f"zips_found={zips}")

    for zip5 in zips:
        mapped = city_from_zip(zip5, zip_index)
        if mapped:
            city = sorted(mapped)[0]
            return {
                "city": city,
                "zip5": zip5,
                "confidence": 0.97,
                "method": "zip",
                "reasons": reasons,
                "normalized_lines": lines,
            }

    city_line = extract_city_state(lines)
    if city_line:
        return {
            "city": city_line,
            "zip5": "",
            "confidence": 0.80,
            "method": "city_state_line",
            "reasons": reasons,
            "normalized_lines": lines,
        }

    city, score = fuzzy_city(lines)
    if city and score >= FUZZY_MIN_SCORE:
        return {
            "city": city,
            "zip5": "",
            "confidence": min(0.75, score),
            "method": "fuzzy",
            "reasons": reasons,
            "normalized_lines": lines,
        }
    if city:
        reasons.append(f"fuzzy best {city!r} scored {score:.3f}, "
                       f"below the {FUZZY_MIN_SCORE:.2f} floor")

    return {
        "city": "unknown",
        "zip5": "",
        "confidence": 0.0,
        "method": "none",
        "reasons": reasons + ["no city match"],
        "normalized_lines": lines,
    }
