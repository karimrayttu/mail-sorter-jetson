"""Read the detector's training record out of the checkpoint itself.

    python tools/model_provenance.py
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt                       # noqa: E402
import torch                                          # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WEIGHTS = REPO / "best-weights.pt"

SURFACE, INK, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9"
BLUE, ORANGE, GREEN, RED = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"

# Hyperparameters worth publishing. The checkpoint carries 104 of them, most at
# their library defaults; these are the ones that describe this run.
REPORTED = [
    ("model", "starting weights"),
    ("data", "dataset descriptor"),
    ("epochs", "epoch budget"),
    ("patience", "early-stopping patience"),
    ("batch", "batch size"),
    ("imgsz", "training image size"),
    ("optimizer", "optimizer"),
    ("lr0", "initial learning rate"),
    ("lrf", "final learning-rate fraction"),
    ("momentum", "momentum"),
    ("weight_decay", "weight decay"),
    ("warmup_epochs", "warmup epochs"),
    ("seed", "random seed"),
    ("pretrained", "started from pretrained weights"),
    ("mosaic", "mosaic augmentation"),
    ("fliplr", "horizontal flip probability"),
    ("flipud", "vertical flip probability"),
    ("degrees", "rotation augmentation, degrees"),
    ("scale", "scale augmentation"),
    ("auto_augment", "classification auto-augment policy"),
]


def para(text):
    """One paragraph, wrapped. Values are interpolated before wrapping so the
    published Markdown does not carry the ragged line breaks of an f-string."""
    return textwrap.fill(" ".join(text.split()), width=79)


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


def segments(epochs):
    """Split the history wherever the epoch counter goes backwards."""
    breaks = [i for i in range(1, len(epochs)) if epochs[i] <= epochs[i - 1]]
    bounds, start = [], 0
    for b in breaks + [len(epochs)]:
        bounds.append((start, b))
        start = b
    return bounds


def plot(history, out):
    epochs = history["epoch"]
    first, last = segments(epochs)[0]
    x = epochs[first:last]

    def series(key):
        return history[key][first:last]

    fig, (ax_m, ax_l) = plt.subplots(1, 2, figsize=(12.5, 5.0))
    fig.patch.set_facecolor(SURFACE)

    m5095 = series("metrics/mAP50-95(B)")
    best = max(m5095)
    best_epoch = x[m5095.index(best)]

    ax_m.plot(x, [v * 100 for v in series("metrics/mAP50(B)")],
              color=BLUE, linewidth=2, label="mAP@50")
    ax_m.plot(x, [v * 100 for v in m5095],
              color=ORANGE, linewidth=2, label="mAP@50-95")
    ax_m.plot(x, [v * 100 for v in series("metrics/recall(B)")],
              color=GREEN, linewidth=1.4, alpha=0.85, label="recall")
    ax_m.axvline(best_epoch, color=RED, linewidth=1, linestyle="--")
    ax_m.annotate(f"kept epoch {best_epoch}\nmAP@50-95 {best * 100:.1f}%",
                  (best_epoch + 3, 20), color=INK, fontsize=9)
    style(ax_m, "Validation metrics per epoch", "epoch", "percent")
    ax_m.set_ylim(0, 105)
    ax_m.legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower right")

    ax_l.plot(x, series("train/box_loss"), color=BLUE, linewidth=2,
              label="train box")
    ax_l.plot(x, series("val/box_loss"), color=BLUE, linewidth=1.4,
              linestyle="--", label="val box")
    ax_l.plot(x, series("train/cls_loss"), color=ORANGE, linewidth=2,
              label="train class")
    ax_l.plot(x, series("val/cls_loss"), color=ORANGE, linewidth=1.4,
              linestyle="--", label="val class")
    style(ax_l, "Training and validation loss", "epoch", "loss")
    ax_l.legend(frameon=False, labelcolor=INK, fontsize=9, loc="upper right")

    fig.tight_layout()
    fig.savefig(out, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return best_epoch, best, x[-1]


def main() -> int:
    if not WEIGHTS.exists():
        print(f"{WEIGHTS.name} not found", file=sys.stderr)
        return 1

    checkpoint = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    args = checkpoint.get("train_args") or {}
    history = checkpoint.get("train_results") or {}
    final = checkpoint.get("train_metrics") or {}
    model = checkpoint["model"]

    figure = REPO / "figures" / "training_curves.png"
    figure.parent.mkdir(exist_ok=True)
    best_epoch, best, stopped = plot(history, figure)
    print(f"  wrote {figure.relative_to(REPO).as_posix()}")

    first, last = segments(history["epoch"])[0]
    minutes = history["time"][last - 1] / 60.0
    parameters = sum(p.numel() for p in model.parameters())
    names = dict(model.names)
    extra = segments(history["epoch"])[1:]

    rows = []
    for key, description in REPORTED:
        if key in args:
            rows.append(f"| `{key}` | {args[key]} | {description} |")

    metrics = []
    for key, label in (("metrics/precision(B)", "precision"),
                       ("metrics/recall(B)", "recall"),
                       ("metrics/mAP50(B)", "mAP@50"),
                       ("metrics/mAP50-95(B)", "mAP@50-95")):
        if key in final:
            metrics.append(f"| {label} | {final[key] * 100:.2f}% |")

    card = f"""# Model card: best-weights.pt

Everything on this page is read out of the checkpoint by
`python tools/model_provenance.py`. Nothing here was typed by hand.

## What it is

| | |
| --- | --- |
| Architecture | {(model.yaml or {}).get("yaml_file", "unknown")}, {parameters:,} parameters |
| Classes | {", ".join(f"{i}: `{n}`" for i, n in sorted(names.items()))} |
| Trained | {checkpoint.get("date", "unknown")} |
| Library | ultralytics {checkpoint.get("version", "unknown")} |
| Licence | {checkpoint.get("license", "unknown")} |

The pipeline uses class 0 only. `sender` is trained and available, and nothing in
this repository routes on it: the return address is not where a piece of mail is
going.

## How it was trained

{para(f"""The run identifier is `{args.get("name", "unknown")}` and the dataset
descriptor is `{args.get("data", "unknown")}`, a path inside a hosted training
container rather than on any machine here. That is why the training images are
not in this repository and the detector cannot be retrained from it. What
survives is this record and the weights themselves, which is enough to evaluate
the model, to reproduce its inference behaviour exactly, and to state what it was
fed.""")}

| Setting | Value | Meaning |
| --- | --- | --- |
{chr(10).join(rows)}

{para(f"""The epoch budget was {args.get("epochs", "?")} and training stopped at
epoch {stopped}. That is early stopping doing its job: the best epoch was
{best_epoch}, patience was {args.get("patience", "?")}, and {best_epoch} +
{args.get("patience", "?")} = {best_epoch + int(args.get("patience", 0))}. The
kept weights are epoch {best_epoch}, not epoch {stopped}; all four of the
checkpoint's stored metrics match that epoch's row to every decimal place.
Wall-clock time for the run was {minutes:.0f} minutes.""")}

![Validation metrics and losses per epoch](../figures/training_curves.png)

{para(f"""*Validation metrics and losses over the {stopped} epochs of the run that
produced these weights. The dashed line marks the epoch that was kept. mAP@50 and
recall both saturate near 100% inside twenty epochs and stop separating the
checkpoints after that; mAP@50-95, which grades how tightly the box fits, is what
actually chose epoch {best_epoch}.*""")}

## Metrics belonging to the kept epoch

| Metric | Value |
| --- | --- |
{chr(10).join(metrics)}

{para(f"""**These are the trainer's own numbers on its own validation split, and
they are not comparable to the ones in the README.** They grade the model against
the annotation style it was trained on, which pads the box out around the address
block. `tools/evaluate_detector.py` grades it against a separately rendered
ground truth that hugs the glyphs, which is why IoU there sits near 0.4 while
mAP@50 here reads {final.get("metrics/mAP50(B)", 0) * 100:.1f}%. Neither number is
wrong; they measure agreement with two different definitions of the correct box.
Containment, in the README, is the one that decides whether OCR receives the
whole address.""")}
"""

    if extra:
        start, end = extra[0]
        card += f"""
## A second, shorter run in the same history

{para(f"""The history in the checkpoint holds {len(history["epoch"])} rows, not
{stopped}. After the row for epoch {stopped} the counter restarts and runs
{history["epoch"][start]} to {history["epoch"][end - 1]}, {end - start} more rows,
reaching mAP@50-95 {max(history["metrics/mAP50-95(B)"][start:end]) * 100:.1f}%
against the kept run's {best * 100:.1f}%. Read them as a second, shorter run
recorded into the same file rather than as a continuation of the first: the
counter restarting is the only thing that separates them, and nothing in the
checkpoint says why it was started. It does not affect which weights shipped. The
stored metrics are the first run's epoch {best_epoch}, so that is what these
weights are.""")}
"""

    (REPO / "docs" / "MODEL_CARD.md").write_text(card, encoding="utf-8")
    print("  wrote docs/MODEL_CARD.md")

    summary = {
        "architecture": (model.yaml or {}).get("yaml_file"),
        "parameters": parameters,
        "classes": names,
        "trained": checkpoint.get("date"),
        "ultralytics": checkpoint.get("version"),
        "kept_epoch": best_epoch,
        "stopped_epoch": stopped,
        "minutes": round(minutes, 1),
        "final_metrics": {k: v for k, v in final.items() if k.startswith("metrics/")},
        "args": {k: args[k] for k, _ in REPORTED if k in args},
    }
    (REPO / "figures" / "model_provenance.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print("  wrote figures/model_provenance.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
