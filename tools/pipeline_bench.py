"""Run the real vision pipeline end to end and score every stage.

    python tools/pipeline_bench.py --per-condition 4   # render, run, plot
    python tools/pipeline_bench.py --render-only
    python tools/pipeline_bench.py --no-ocr            # detector only, faster
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from address.address_verify import load_zip_csv, verify_address  # noqa: E402

SURFACE, INK, INK_MUTED, GRID = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9"
# Outcome colours are the reserved status palette: this is a state, not a series.
OUTCOME = [
    ("correct_city", "routed correctly", "#0ca30c"),
    ("rejected", "sent to unknown bin", "#fab219"),
    ("misrouted", "sent to the WRONG city", "#d03b3b"),
]

# Business recipients only. No personal names go in a public repository.
DESTINATIONS = [
    ("Houston", "1200 MAIN ST STE 400", "HOUSTON, TX 77002", "GULF COAST SUPPLY CO"),
    ("San Antonio", "845 COMMERCE ST", "SAN ANTONIO, TX 78205", "ALAMO PARTS DEPOT"),
    ("Dallas", "400 ELM ST FL 2", "DALLAS, TX 75202", "TRINITY LOGISTICS LLC"),
    ("Austin", "615 CONGRESS AVE", "AUSTIN, TX 78701", "COLORADO RIVER TRADING"),
    ("Lubbock", "2100 BROADWAY", "LUBBOCK, TX 79401", "SOUTH PLAINS HARDWARE"),
]
RETURN_BLOCK = ["CENTRAL MAILING SERVICES", "PO BOX 4410", "AMARILLO, TX 79101"]

# Progressively worse capture conditions, the way a conveyor camera degrades.
CONDITIONS = [
    ("clean", dict(blur=0.0, noise=0, angle=0.0, jpeg=95, bright=1.0)),
    ("slight_blur", dict(blur=1.0, noise=3, angle=1.5, jpeg=85, bright=1.0)),
    ("motion", dict(blur=2.0, noise=6, angle=3.0, jpeg=70, bright=0.92)),
    ("dim", dict(blur=1.5, noise=10, angle=2.0, jpeg=60, bright=0.72)),
    ("bad", dict(blur=3.0, noise=16, angle=5.0, jpeg=45, bright=0.65)),
]


def load_font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_envelope(dest, condition, rng, want_box=False):
    """Draw one envelope, then degrade it like a camera would."""
    city, street, city_line, company = dest
    W, H = 1000, 620
    img = Image.new("RGB", (W, H), (247, 245, 238))
    draw = ImageDraw.Draw(img)
    draw.rectangle([6, 6, W - 6, H - 6], outline=(206, 200, 188), width=3)

    small, body, head = load_font(21), load_font(30), load_font(33)

    # Sender block, top left. The detector has a 'sender' class for this.
    for i, line in enumerate(RETURN_BLOCK):
        draw.text((48, 46 + i * 27), line, font=small, fill=(92, 90, 86))

    # Stamp, top right.
    draw.rectangle([W - 172, 40, W - 52, 148], outline=(150, 146, 138), width=3)
    draw.text((W - 156, 82), "POSTAGE", font=small, fill=(150, 146, 138))

    # Receiver block, centre right. This is what YOLO has to find.
    x, y = 330, 300
    draw.text((x, y), company, font=head, fill=(16, 16, 16))
    draw.text((x, y + 46), street, font=body, fill=(16, 16, 16))
    draw.text((x, y + 88), city_line, font=body, fill=(16, 16, 16))

    # Mask of just the receiver block, so the ground-truth box survives rotation.
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((x, y), company, font=head, fill=255)
    mask_draw.text((x, y + 46), street, font=body, fill=255)
    mask_draw.text((x, y + 88), city_line, font=body, fill=255)

    params = condition[1]
    angle = rng.uniform(-params["angle"], params["angle"]) if params["angle"] else 0.0
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(238, 236, 230))
        mask = mask.rotate(angle, resample=Image.NEAREST, fillcolor=0)
    if params["blur"]:
        img = img.filter(ImageFilter.GaussianBlur(params["blur"]))
    if params["bright"] != 1.0:
        img = Image.fromarray(np.clip(np.asarray(img).astype(np.float32)
                                      * params["bright"], 0, 255).astype(np.uint8))
    if params["noise"]:
        arr = np.asarray(img).astype(np.int16)
        # Consume one draw here. It is not used: it is kept so that the noise
        # seed drawn on the next line matches the fixtures already committed
        # under tests/fixtures/envelopes and the OCR strings pinned in
        # tests/test_address_verify.py. Removing it re-renders every fixture.
        rng.choice([-1, 1])
        noise = np.random.default_rng(rng.randrange(1 << 30)).normal(
            0, params["noise"], arr.shape)
        img = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    if want_box:
        return img, mask.getbbox()
    return img


def render_all(out_dir: Path, per_condition: int, rng):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear first. Changing --per-condition used to leave the previous run's
    # JPGs next to a manifest that no longer listed them, so the directory on
    # disk and manifest.json could come from two different runs.
    for stale in list(out_dir.glob("*.jpg")) + list(out_dir.glob("manifest.json")):
        stale.unlink()
    manifest = []
    for cond in CONDITIONS:
        for i in range(per_condition):
            dest = DESTINATIONS[i % len(DESTINATIONS)]
            img = render_envelope(dest, cond, rng)
            name = f"{cond[0]}_{i:02d}_{dest[0].replace(' ', '')}.jpg"
            path = out_dir / name
            img.save(path, quality=cond[1]["jpeg"])
            # Repo-relative, so the manifest carries no machine identity.
            manifest.append({"path": path.relative_to(REPO).as_posix(),
                             "condition": cond[0], "truth_city": dest[0]})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                           encoding="utf-8")
    return manifest


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


def plot_stages(rows, out_dir: Path):
    order = [c[0] for c in CONDITIONS]
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    fig.patch.set_facecolor(SURFACE)
    width, xs = 0.26, np.arange(len(order))

    for i, (stage, label, color) in enumerate(OUTCOME):
        vals = []
        for cond in order:
            subset = [r for r in rows if r["condition"] == cond]
            vals.append(100.0 * sum(bool(r[stage]) for r in subset) / max(1, len(subset)))
        bars = ax.bar(xs + (i - 1) * width, vals, width * 0.92,
                      color=color, label=label,
                      edgecolor=SURFACE, linewidth=2)
        for bar, v in zip(bars, vals):
            ax.annotate(f"{v:.0f}", (bar.get_x() + bar.get_width() / 2, v),
                        textcoords="offset points", xytext=(0, 4),
                        ha="center", color=INK, fontsize=8)

    ax.set_xticks(xs)
    ax.set_xticklabels(order)
    ax.set_ylim(0, 112)
    style(ax, "Sorting outcome by capture condition", "Capture condition",
          "Envelopes (%)")
    ax.legend(frameon=False, labelcolor=INK, fontsize=9, ncol=3,
              loc="lower center", bbox_to_anchor=(0.5, -0.24))
    fig.tight_layout()
    fig.savefig(out_dir / "sorting_outcome.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def stage_medians(rows):
    """Median, not mean, per stage."""
    stages = [("detect_ms", "YOLO detect"), ("ocr_ms", "EasyOCR read"),
              ("verify_ms", "address match")]
    return stages, [float(np.median([r[k] for r in rows if r[k] is not None] or [0]))
                    for k, _ in stages]


def plot_latency(rows, out_dir: Path):
    stages, medians = stage_medians(rows)

    fig, ax = plt.subplots(figsize=(9, 3.6))
    fig.patch.set_facecolor(SURFACE)
    bars = ax.barh([label for _, label in stages], medians,
                   color=["#2a78d6", "#eb6834", "#1baf7a"], height=0.55)
    for bar, v in zip(bars, medians):
        ax.annotate(f"{v:.1f} ms", (v, bar.get_y() + bar.get_height() / 2),
                    textcoords="offset points", xytext=(6, 0), va="center",
                    color=INK, fontsize=9)
    style(ax, "Median time per envelope, measured on this machine, one run",
          "Milliseconds", "")
    ax.margins(x=0.18)
    fig.tight_layout()
    fig.savefig(out_dir / "stage_latency.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", default="best-weights.pt")
    ap.add_argument("--csv", default="data/tx_zip_city.example.csv")
    # 4 is the run every committed number comes from: the figures, the README
    # tables and the OCR strings pinned in tests/test_address_verify.py. Change
    # it and the fixtures, and therefore the OCR output, all change with it.
    ap.add_argument("--per-condition", type=int, default=4)
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()

    rng = random.Random(7)
    fixtures = REPO / "tests" / "fixtures" / "envelopes"
    manifest = render_all(fixtures, args.per_condition, rng)
    print(f"rendered {len(manifest)} envelopes into "
          f"{fixtures.relative_to(REPO)}")
    if args.render_only:
        return

    from vision.yolo_receiver import ReceiverDetector, torch_device  # noqa: E402
    detector = ReceiverDetector(str(REPO / args.weights))
    # torch_device() is what the detector actually runs on. The old banner
    # printed cuda/cpu from detector.class_id, which is a class-name lookup and
    # said "cuda" on a machine with no GPU at all.
    print(f"loaded {args.weights}: classes={detector.model.names} "
          f"device={torch_device()}")

    reader = None
    if not args.no_ocr:
        from vision.ocr_reader import OCRReader                # noqa: E402
        reader = OCRReader(use_easy=True, use_trocr=False)

    zip_index = load_zip_csv(str(REPO / args.csv))
    rows = []

    # Warm-up, not timed. The first detect of a process pays model load and
    # CUDA context setup - about 400 ms - and folding that into the first
    # envelope skews every aggregate over a 20-envelope run.
    warm = cv2.imread(str(REPO / manifest[0]["path"]))
    warm_crop, _ = detector.detect_best_crop(warm)
    if reader is not None:
        reader.read(Image.fromarray(cv2.cvtColor(
            warm_crop if warm_crop is not None and warm_crop.size else warm,
            cv2.COLOR_BGR2RGB)))

    for item in manifest:
        frame = cv2.imread(str(REPO / item["path"]))
        row = {"condition": item["condition"], "truth_city": item["truth_city"],
               "detected": False, "ocr_text": "", "city": None,
               "correct_city": False, "rejected": False, "misrouted": False,
               "detect_ms": None, "ocr_ms": None, "verify_ms": None}

        t0 = time.perf_counter()
        crop, _ = detector.detect_best_crop(frame)
        row["detect_ms"] = (time.perf_counter() - t0) * 1000.0
        row["detected"] = crop is not None and crop.size > 0

        source = crop if row["detected"] else frame
        if reader is not None:
            pil = Image.fromarray(cv2.cvtColor(source, cv2.COLOR_BGR2RGB))
            t0 = time.perf_counter()
            best, candidates = reader.read(pil)
            row["ocr_ms"] = (time.perf_counter() - t0) * 1000.0
            row["ocr_text"] = best
            t0 = time.perf_counter()
            result = verify_address(candidates or [best], zip_index)
            row["verify_ms"] = (time.perf_counter() - t0) * 1000.0
            row["city"] = result["city"]
            row["method"] = result["method"]
            row["correct_city"] = (result["city"].lower()
                                   == item["truth_city"].lower())
            # A reject costs a manual re-run. A misroute puts the piece on a
            # truck to another city, so the two are counted separately.
            row["rejected"] = result["city"].lower() == "unknown"
            row["misrouted"] = not row["correct_city"] and not row["rejected"]
        rows.append(row)

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'condition':<14}{'detect':>8}{'correct':>9}{'reject':>8}"
          f"{'MISROUTE':>10}{'det ms':>9}{'ocr ms':>9}")
    for cond, _ in CONDITIONS:
        sub = [r for r in rows if r["condition"] == cond]
        if not sub:
            continue
        pct = lambda key: 100.0 * sum(bool(r[key]) for r in sub) / len(sub)
        dms = float(np.mean([r["detect_ms"] for r in sub]))
        oms = float(np.mean([r["ocr_ms"] for r in sub if r["ocr_ms"]] or [0]))
        print(f"{cond:<14}{pct('detected'):>7.0f}%{pct('correct_city'):>8.0f}%"
              f"{pct('rejected'):>7.0f}%{pct('misrouted'):>9.0f}%"
              f"{dms:>9.1f}{oms:>9.1f}")

    misroutes = sum(r["misrouted"] for r in rows)
    print(f"\nmisrouted {misroutes}/{len(rows)} envelopes "
          f"({100.0 * misroutes / len(rows):.0f}%)")

    if not args.no_ocr:
        stages, medians = stage_medians(rows)
        total = sum(medians)
        parts = "  ".join(f"{label} {v:.1f}" for (_, label), v in zip(stages, medians))
        print(f"median ms per envelope: {parts}  ->  {total:.1f} ms total, "
              f"{1000.0 / total:.1f} envelopes/s on {torch_device()} "
              f"(one run; repeat runs vary, see README)")

    (out_dir / "pipeline_results.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8")
    plot_stages(rows, out_dir)
    if not args.no_ocr:
        plot_latency(rows, out_dir)
    print(f"\nwrote {args.out}/sorting_outcome.png")
    print(f"wrote {args.out}/pipeline_results.json")


if __name__ == "__main__":
    main()
