# Model card: best-weights.pt

Everything on this page is read out of the checkpoint by
`python tools/model_provenance.py`. Nothing here was typed by hand.

## What it is

| | |
| --- | --- |
| Architecture | yolo11s.yaml, 9,428,566 parameters |
| Classes | 0: `receiver`, 1: `sender` |
| Trained | 2025-11-05T16:27:29.609204 |
| Library | ultralytics 8.3.171 |
| Licence | AGPL-3.0 (https://ultralytics.com/license) |

The pipeline uses class 0 only. `sender` is trained and available, and nothing in
this repository routes on it: the return address is not where a piece of mail is
going.

## How it was trained

The run identifier is `roboflow_train` and the dataset descriptor is
`/train/cache/dataset/data.yaml`, a path inside a hosted training container
rather than on any machine here. That is why the training images are not in
this repository and the detector cannot be retrained from it. What survives is
this record and the weights themselves, which is enough to evaluate the model,
to reproduce its inference behaviour exactly, and to state what it was fed.

| Setting | Value | Meaning |
| --- | --- | --- |
| `model` | yolo11s.pt | starting weights |
| `data` | /train/cache/dataset/data.yaml | dataset descriptor |
| `epochs` | 300 | epoch budget |
| `patience` | 90 | early-stopping patience |
| `batch` | 10 | batch size |
| `imgsz` | 1024 | training image size |
| `optimizer` | auto | optimizer |
| `lr0` | 0.01 | initial learning rate |
| `lrf` | 0.01 | final learning-rate fraction |
| `momentum` | 0.937 | momentum |
| `weight_decay` | 0.0005 | weight decay |
| `warmup_epochs` | 3.0 | warmup epochs |
| `seed` | 0 | random seed |
| `pretrained` | True | started from pretrained weights |
| `mosaic` | 1.0 | mosaic augmentation |
| `fliplr` | 0.5 | horizontal flip probability |
| `flipud` | 0.0 | vertical flip probability |
| `degrees` | 0.0 | rotation augmentation, degrees |
| `scale` | 0.5 | scale augmentation |
| `auto_augment` | randaugment | classification auto-augment policy |

The epoch budget was 300 and training stopped at epoch 146. That is early
stopping doing its job: the best epoch was 56, patience was 90, and 56 + 90 =
146. The kept weights are epoch 56, not epoch 146; all four of the checkpoint's
stored metrics match that epoch's row to every decimal place. Wall-clock time
for the run was 40 minutes.

![Validation metrics and losses per epoch](../figures/training_curves.png)

*Validation metrics and losses over the 146 epochs of the run that produced
these weights. The dashed line marks the epoch that was kept. mAP@50 and recall
both saturate near 100% inside twenty epochs and stop separating the
checkpoints after that; mAP@50-95, which grades how tightly the box fits, is
what actually chose epoch 56.*

## Metrics belonging to the kept epoch

| Metric | Value |
| --- | --- |
| precision | 98.73% |
| recall | 100.00% |
| mAP@50 | 99.50% |
| mAP@50-95 | 63.37% |

**These are the trainer's own numbers on its own validation split, and they are
not comparable to the ones in the README.** They grade the model against the
annotation style it was trained on, which pads the box out around the address
block. `tools/evaluate_detector.py` grades it against a separately rendered
ground truth that hugs the glyphs, which is why IoU there sits near 0.4 while
mAP@50 here reads 99.5%. Neither number is wrong; they measure agreement with
two different definitions of the correct box. Containment, in the README, is
the one that decides whether OCR receives the whole address.

## A second, shorter run in the same history

The history in the checkpoint holds 156 rows, not 146. After the row for epoch
146 the counter restarts and runs 57 to 66, 10 more rows, reaching mAP@50-95
60.6% against the kept run's 63.4%. Read them as a second, shorter run recorded
into the same file rather than as a continuation of the first: the counter
restarting is the only thing that separates them, and nothing in the checkpoint
says why it was started. It does not affect which weights shipped. The stored
metrics are the first run's epoch 56, so that is what these weights are.
