"""OCR reader for the receiver crop.

EasyOCR is fast enough for testing. TrOCR can help with handwritten labels, but it is heavier.
"""

import re
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageOps

try:
    import torch
except Exception:
    torch = None

try:
    from easyocr import Reader as EasyOCRReader
except Exception as exc:
    EasyOCRReader = None
    EASY_IMPORT_ERROR = exc
else:
    EASY_IMPORT_ERROR = None

try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
except Exception as exc:
    TrOCRProcessor = None
    VisionEncoderDecoderModel = None
    TROCR_IMPORT_ERROR = exc
else:
    TROCR_IMPORT_ERROR = None


def device() -> str:
    if torch is not None and torch.cuda.is_available():
        return "cuda"
    return "cpu"


def preprocess_roi(pil_img: Image.Image) -> Image.Image:
    img = ImageOps.autocontrast(pil_img.convert("RGB"), cutoff=2)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))
    w, h = img.size
    scale = 1.8 if max(w, h) < 720 else 1.3
    return img.resize((int(w * scale), int(h * scale)))


class OCRReader:
    def __init__(self, use_easy: bool = True, use_trocr: bool = False):
        self.use_easy = use_easy
        self.use_trocr = use_trocr
        self.easy = None
        self.trocr_processor = None
        self.trocr_model = None

        if self.use_easy:
            if EasyOCRReader is None:
                raise RuntimeError(f"EasyOCR is not available: {EASY_IMPORT_ERROR}")
            self.easy = EasyOCRReader(("en",), gpu=(device() == "cuda"))

        if self.use_trocr:
            if TrOCRProcessor is None or VisionEncoderDecoderModel is None or torch is None:
                raise RuntimeError(f"TrOCR dependencies are not available: {TROCR_IMPORT_ERROR}")
            self.trocr_processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
            self.trocr_model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten").to(device()).eval()

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r'[^A-Za-z0-9 ,.\-#/:"]', " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def read(self, roi_pil: Image.Image) -> Tuple[str, List[str]]:
        image = preprocess_roi(roi_pil)
        candidates: List[str] = []

        if self.easy is not None:
            arr = np.asarray(image)
            lines = self.easy.readtext(arr, detail=0)
            lines = [self._clean(line) for line in lines if line and line.strip()]
            candidates.extend(lines)
            if lines:
                candidates.append(" ".join(lines))

        if self.trocr_model is not None:
            with torch.no_grad():
                pixel_values = self.trocr_processor(images=image, return_tensors="pt").pixel_values.to(device())
                ids = self.trocr_model.generate(pixel_values, max_new_tokens=128, num_beams=8, no_repeat_ngram_size=3)
                text = self.trocr_processor.batch_decode(ids, skip_special_tokens=True)[0]
                candidates.append(self._clean(text))

        candidates = [c for c in candidates if c]
        return self._pick_best(candidates), candidates

    def _pick_best(self, candidates: List[str]) -> str:
        def score(text: str) -> float:
            points = min(len(text) / 30.0, 1.0)
            if re.search(r"\b\d{5}(?:-\d{4})?\b", text):
                points += 3.0
            if re.search(r"[A-Za-z][A-Za-z .'-]+,\s*[A-Z]{2}", text):
                points += 2.0
            if re.search(r"^\s*\d{2,6}\s+[A-Za-z0-9 .'-]+", text):
                points += 1.0
            return points

        return max(candidates, key=score) if candidates else ""
