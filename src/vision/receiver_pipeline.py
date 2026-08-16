#!/usr/bin/env python3
"""Camera -> YOLO receiver crop -> OCR -> destination city.

This file is for vision testing by itself. The hardware loop can call the same pieces later.
"""

import argparse
import os
import sys
from collections import Counter, deque

import cv2
from PIL import Image

# Allow running this file directly from src/vision.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from address.address_verify import load_zip_csv, verify_address
from vision.ocr_reader import OCRReader
from vision.yolo_receiver import ReceiverDetector, draw_detection


def load_zip_index(path: str):
    if not path:
        return {"exact": {}, "prefix": {}}
    return load_zip_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Receiver label detector + OCR test")
    parser.add_argument("--weights", required=True, help="YOLO .pt weights")
    parser.add_argument("--receiver", default="receiver", help="YOLO class name or class index")
    parser.add_argument("--source", default="0", help="camera index or video path")
    parser.add_argument("--zip-csv", default="", help="optional ZIP/city CSV")
    parser.add_argument("--use-trocr", action="store_true", help="enable TrOCR in addition to EasyOCR")
    args = parser.parse_args()

    detector = ReceiverDetector(args.weights, receiver_class=args.receiver)
    ocr = OCRReader(use_easy=True, use_trocr=args.use_trocr)
    zip_index = load_zip_index(args.zip_csv)

    source = 0 if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera/video source: {args.source}")

    stable_results = deque(maxlen=5)
    stable_text = ""
    print("Press q to quit.")

    # try/finally, because an exception out of the detector, the OCR or imshow
    # used to leave the USB camera claimed and the windows up. On a bench with
    # one camera that means the next run cannot open the device.
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            crop, box = detector.detect_best_crop(frame)
            city = "unknown"

            if crop is not None:
                pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                best_text, all_lines = ocr.read(pil)
                result = verify_address(all_lines if all_lines else [best_text], zip_index=zip_index)
                city = result["city"]
                stable_results.append(city)
                stable_text = Counter(stable_results).most_common(1)[0][0]

            label = stable_text if stable_text else city
            draw_detection(frame, box, label)
            cv2.imshow("Mail sorter - receiver OCR", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
