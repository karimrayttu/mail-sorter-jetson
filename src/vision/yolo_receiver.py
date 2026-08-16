"""YOLO helper for finding the receiver/address area in a camera frame."""

from typing import Optional, Tuple

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except Exception as exc:
    YOLO = None
    YOLO_IMPORT_ERROR = exc
else:
    YOLO_IMPORT_ERROR = None

try:
    import torch
except Exception:
    torch = None


def torch_device() -> str:
    if torch is not None and torch.cuda.is_available():
        return "cuda"
    return "cpu"


class ReceiverDetector:
    def __init__(self, weights_path: str, receiver_class="receiver", imgsz: int = 960, conf: float = 0.25):
        if YOLO is None:
            raise RuntimeError(f"ultralytics is not available: {YOLO_IMPORT_ERROR}")

        self.model = YOLO(weights_path)
        self.receiver_class = receiver_class
        self.imgsz = imgsz
        self.conf = conf
        self.class_id = self._resolve_class_id(receiver_class)

    def _resolve_class_id(self, receiver_class) -> Optional[int]:
        names = getattr(self.model.model, "names", None)
        if names is None:
            return None

        try:
            return int(receiver_class)
        except Exception:
            pass

        for idx, name in names.items():
            if str(name).lower() == str(receiver_class).lower():
                return int(idx)
        return None

    def detect_best_crop(self, frame_bgr: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[tuple]]:
        device_arg = 0 if torch_device() == "cuda" else None
        results = self.model.predict(frame_bgr, imgsz=self.imgsz, conf=self.conf, device=device_arg, verbose=False)
        if not results:
            return None, None

        result = results[0]
        h, w = frame_bgr.shape[:2]
        best_crop = None
        best_box = None
        best_area = -1

        # Segmentation masks are nicer if the model has them.
        if getattr(result, "masks", None) is not None and result.masks.data is not None:
            masks = result.masks.data.cpu().numpy().astype(np.uint8)
            for i, cls in enumerate(result.boxes.cls.tolist()):
                if self.class_id is not None and int(cls) != self.class_id:
                    continue
                ys, xs = np.where(masks[i] > 0)
                if xs.size == 0:
                    continue
                x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
                crop, box, area = self._crop_with_pad(frame_bgr, x0, y0, x1, y1, w, h)
                if area > best_area:
                    best_crop, best_box, best_area = crop, box, area

        # Normal bounding boxes are the fallback.
        if best_crop is None and result.boxes is not None:
            for xyxy, cls in zip(result.boxes.xyxy.tolist(), result.boxes.cls.tolist()):
                if self.class_id is not None and int(cls) != self.class_id:
                    continue
                x0, y0, x1, y1 = map(int, xyxy)
                crop, box, area = self._crop_with_pad(frame_bgr, x0, y0, x1, y1, w, h)
                if area > best_area:
                    best_crop, best_box, best_area = crop, box, area

        return best_crop, best_box

    @staticmethod
    def _crop_with_pad(frame_bgr, x0, y0, x1, y1, w, h):
        pad = int(0.04 * max(x1 - x0, y1 - y0))
        x0 = max(0, int(x0) - pad)
        y0 = max(0, int(y0) - pad)
        x1 = min(w, int(x1) + pad)
        y1 = min(h, int(y1) + pad)
        area = max(0, x1 - x0) * max(0, y1 - y0)
        return frame_bgr[y0:y1, x0:x1], (x0, y0, x1, y1), area


def draw_detection(frame_bgr, box, label: str = "receiver") -> None:
    if box is None:
        return
    x0, y0, x1, y1 = map(int, box)
    cv2.rectangle(frame_bgr, (x0, y0), (x1, y1), (50, 220, 50), 2)
    cv2.putText(frame_bgr, label[:60], (x0, max(24, y0 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 220, 50), 2)
