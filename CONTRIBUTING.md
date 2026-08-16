# Contributing

This is a conveyor mail sorter: detector, OCR, address matcher and bin control.
The vision stage and the motion stage fail in different ways, so they are
deliberately separable and testable on their own.

## Before you open a pull request

Run the checks. They are fast, they need no hardware, and they are the same
ones used while the work was done.

```bash
python tests/test_address_verify.py
python tools/check_bin_maps.py
python tools/pipeline_bench.py --per-condition 4
python tools/evaluate_detector.py
```

What each one is for:

- `python tests/test_address_verify.py`: matcher behaviour plus the misroute regression pinned to real OCR output
- `python tools/check_bin_maps.py`: the two copies of the bin angle table must agree
- `python tools/pipeline_bench.py --per-condition 4`: runs the shipped weights and real OCR end to end; this is where the committed figures come from
- `python tools/evaluate_detector.py`: scores the detector against ground-truth boxes

A change that makes a check fail needs the check updated in the same commit,
with the reason in the message. Do not skip or delete a check to make it pass.

## House rules

- Numbers in documentation must be reproducible by a command in this repository.
  If you cannot generate it, do not write it.
- No personal names, instrument serial numbers, MAC or IP addresses, or absolute
  paths in committed files.
- Keep any value defined in exactly one place. Several checks here exist only
  because a constant was once written down twice and drifted.

## Useful things to work on

- Real photographed envelopes to replace the rendered fixtures in the bench.
- More cities. `ALLOWED` and the bin angle tables are the two places to touch.
- A measured pieces-per-minute figure for the whole machine, which nothing here states.

## Licence

Contributions are accepted under the MIT licence in `LICENSE`.
