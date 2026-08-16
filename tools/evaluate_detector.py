"""Score the trained receiver detector against known ground truth.

    python tools/evaluate_detector.py
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from pipeline_bench import CONDITIONS, DESTINATIONS, render_envelope  # noqa: E402

SURFACE, INK, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9"
BLUE, ORANGE, GREEN, RED = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"


def style(ax, title, xlabel, ylabel):
    ax.set_title(title, color=INK, fontsize=12, pad=12, loc="left")
    ax.set_xlabel(xlabel, color=INK_MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=INK_MUTED, fontsize=9)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")


def intersection(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    return max(0, ix1 - ix0) * max(0, iy1 - iy0)


def iou(a, b):
    inter = intersection(a, b)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def containment(prediction, truth):
    """Fraction of the true block that lands inside the predicted crop."""
    area = (truth[2] - truth[0]) * (truth[3] - truth[1])
    return intersection(prediction, truth) / area if area else 0.0


def plot_iou(rows, out):
    order = [c[0] for c in CONDITIONS]
    fig, (ax_c, ax_i) = plt.subplots(1, 2, figsize=(12.5, 5.2))
    fig.patch.set_facecolor(SURFACE)

    for ax, key, color, title, ylabel in (
            (ax_c, "containment", GREEN,
             "Address block captured by the crop",
             "Fraction of the true block inside the crop"),
            (ax_i, "iou", BLUE,
             "Box agreement with the tight glyph extent",
             "IoU against the true block")):
        data = [[r[key] for r in rows if r["condition"] == c] for c in order]
        bp = ax.boxplot(data, patch_artist=True, widths=0.55,
                        medianprops=dict(color=INK, linewidth=1.6),
                        whiskerprops=dict(color="#c3c2b7"),
                        capprops=dict(color="#c3c2b7"),
                        flierprops=dict(marker="o", markersize=4,
                                        markerfacecolor=INK_MUTED,
                                        markeredgecolor="none", alpha=0.6))
        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_edgecolor(SURFACE)
            patch.set_linewidth(2)
        ax.set_xticks(range(1, len(order) + 1))
        ax.set_xticklabels(order, fontsize=8, rotation=20)
        ax.set_ylim(0, 1.05)
        style(ax, title, "", ylabel)

    ax_i.axhline(0.5, color=RED, linewidth=1, linestyle="--")
    ax_i.annotate("IoU 0.5", (0.6, 0.52), color=INK, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "detector_localisation.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def plot_pr(rows, out):
    """Precision and recall as the IoU acceptance threshold tightens."""
    thresholds = np.arange(0.30, 0.96, 0.05)
    total = len(rows)
    precisions, recalls = [], []
    for t in thresholds:
        hits = sum(1 for r in rows if r["detected"] and r["iou"] >= t)
        detected = sum(1 for r in rows if r["detected"])
        precisions.append(hits / detected if detected else 0.0)
        recalls.append(hits / total)

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(SURFACE)
    ax.plot(thresholds, [p * 100 for p in precisions], color=BLUE, linewidth=2,
            marker="o", markersize=7, markeredgecolor=SURFACE,
            markeredgewidth=1.5, label="precision")
    ax.plot(thresholds, [r * 100 for r in recalls], color=ORANGE, linewidth=2,
            marker="s", markersize=7, markeredgecolor=SURFACE,
            markeredgewidth=1.5, label="recall")
    style(ax, "Detector precision and recall against the IoU threshold",
          "IoU threshold", "Percent of envelopes")
    ax.set_ylim(0, 105)
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower left")
    fig.tight_layout()
    fig.savefig(out / "detector_precision_recall.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return {round(float(t), 2): {"precision": round(p, 4), "recall": round(r, 4)}
            for t, p, r in zip(thresholds, precisions, recalls)}


def plot_examples(examples, out):
    """One detection per condition, drawn over the frame it came from."""
    fig, axes = plt.subplots(1, len(examples), figsize=(4.1 * len(examples), 3.4))
    fig.patch.set_facecolor(SURFACE)
    for ax, ex in zip(np.atleast_1d(axes), examples):
        frame = cv2.cvtColor(ex["frame"], cv2.COLOR_BGR2RGB)
        ax.imshow(frame)
        tx0, ty0, tx1, ty1 = ex["truth"]
        ax.add_patch(plt.Rectangle((tx0, ty0), tx1 - tx0, ty1 - ty0,
                                   fill=False, edgecolor=GREEN, linewidth=2.2))
        if ex["box"]:
            px0, py0, px1, py1 = ex["box"]
            ax.add_patch(plt.Rectangle((px0, py0), px1 - px0, py1 - py0,
                                       fill=False, edgecolor=BLUE, linewidth=2.2,
                                       linestyle="--"))
        ax.set_title(f"{ex['condition']}  IoU {ex['iou']:.2f}", color=INK,
                     fontsize=10, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
        for side in ax.spines.values():
            side.set_visible(False)
    fig.suptitle("Green is the true receiver block, dashed blue is the detection",
                 color=INK_MUTED, fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out / "detector_examples.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default="best-weights.pt")
    ap.add_argument("--per-condition", type=int, default=6)
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()

    from vision.yolo_receiver import ReceiverDetector, torch_device  # noqa: E402

    detector = ReceiverDetector(str(REPO / args.weights))
    # device=0 was hard-coded here, which crashes on a machine without CUDA.
    device_arg = 0 if torch_device() == "cuda" else None
    print(f"weights {args.weights}  classes {detector.model.names}  "
          f"device {torch_device()}")

    rng = random.Random(11)
    rows, examples = [], []

    for condition in CONDITIONS:
        for i in range(args.per_condition):
            dest = DESTINATIONS[i % len(DESTINATIONS)]
            img, truth = render_envelope(dest, condition, rng, want_box=True)
            frame = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)

            results = detector.model.predict(
                frame, imgsz=detector.imgsz, conf=detector.conf,
                device=device_arg, verbose=False)
            box, confidence = None, 0.0
            if results and results[0].boxes is not None:
                for xyxy, cls, conf in zip(results[0].boxes.xyxy.tolist(),
                                           results[0].boxes.cls.tolist(),
                                           results[0].boxes.conf.tolist()):
                    if detector.class_id is not None and int(cls) != detector.class_id:
                        continue
                    if conf > confidence:
                        box, confidence = tuple(map(int, xyxy)), float(conf)

            overlap = iou(box, truth) if box else 0.0
            covered = containment(box, truth) if box else 0.0
            rows.append({"condition": condition[0], "detected": box is not None,
                         "iou": overlap, "containment": covered,
                         "confidence": confidence})
            if i == 0:
                examples.append({"condition": condition[0], "frame": frame,
                                 "truth": truth, "box": box, "iou": overlap})

    out = REPO / args.out
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n{'condition':<14}{'found':>7}{'contained':>11}{'mean IoU':>10}"
          f"{'mean conf':>11}")
    summary = {}
    for cond, _ in CONDITIONS:
        sub = [r for r in rows if r["condition"] == cond]
        found = 100.0 * sum(r["detected"] for r in sub) / len(sub)
        ious = [r["iou"] for r in sub]
        confs = [r["confidence"] for r in sub if r["detected"]]
        covered = [r["containment"] for r in sub]
        summary[cond] = {"found_pct": round(found, 1),
                         "mean_containment": round(float(np.mean(covered)), 4),
                         "min_containment": round(float(np.min(covered)), 4),
                         "mean_iou": round(float(np.mean(ious)), 4),
                         "min_iou": round(float(np.min(ious)), 4),
                         "mean_conf": round(float(np.mean(confs)) if confs else 0.0, 4)}
        print(f"{cond:<14}{found:>6.0f}%{np.mean(covered):>11.3f}"
              f"{np.mean(ious):>10.3f}{np.mean(confs) if confs else 0:>11.3f}")

    plot_iou(rows, out)
    pr = plot_pr(rows, out)
    plot_examples(examples, out)

    (out / "detector_metrics.json").write_text(
        json.dumps({"per_condition": summary, "precision_recall_by_iou": pr},
                   indent=2), encoding="utf-8")
    print(f"\nwrote 3 figures and {args.out}/detector_metrics.json")


if __name__ == "__main__":
    main()
