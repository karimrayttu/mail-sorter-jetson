# Bill of Materials

Parts for the mail sorter: camera, envelope-detect photogate, conveyor drive, and the
rotating bin with its shaft encoder. Prices are what the part cost at the time of
sourcing, not a current quote. "In stock" means the part was already on the bench and
was not purchased for this build.

Supplier links are bare product links; tracking and affiliate parameters have been
stripped.

## Compute

| Part | Notes | Price | Link |
| --- | --- | ---: | --- |
| NVIDIA Jetson AGX Orin Developer Kit | Runs the detector and the OCR stage, and drives the steppers, the photogate and the encoder off its 40-pin header. Already on the bench; not part of the purchased total below. | in stock | [NVIDIA](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/) |

## Vision

| Part | Notes | Price | Link |
| --- | --- | ---: | --- |
| Raspberry Pi Camera Module v3 (autofocus) | Autofocus was the deciding feature; fixed-focus modules smear the address block at conveyor distance. | $29 | [Digi-Key SC1223](https://www.digikey.com/en/products/detail/raspberry-pi/SC1223/17278639) |
| CSI ribbon cable, extended length | Reaches from the board to the camera mount over the belt. | $3 | [Digi-Key 2143](https://www.digikey.com/en/products/detail/adafruit-industries-llc/2143/8323739) |
| IR reflective photogate | Trips when an envelope reaches the capture spot, which is what gates the frame grab. | $8 | [Amazon B0CLD3ZRTY](https://www.amazon.com/dp/B0CLD3ZRTY) |

## Rotating bin

| Part | Notes | Price | Link |
| --- | --- | ---: | --- |
| AS5048A magnetic encoder, adapter board | Originally specified. See the substitution note below. | $16 | [Digi-Key AS5048A-ADAPTERBOARD](https://www.digikey.com/en/products/detail/ams-osram-usa-inc/AS5048A-ADAPTERBOARD/3188612) |
| Diametrically magnetised disc magnet, N35, 8 mm x 3 mm | Sits on the bin shaft, directly under the encoder die. | $3 | [radialmagnet.com](https://radialmagnet.com/our-magnets/neodymium-magnet-disk-n35-8mm-x-3mma/) / [Digi-Key 9083](https://www.digikey.com/en/products/detail/radial-magnets-inc/9083/22935780) |
| NEMA 17 stepper | Turns the six-partition plate. | in stock | n/a |
| DRV8825 stepper driver | | in stock | n/a |
| Rotating plate, six partitions | 3D printed. | printed | n/a |

## Conveyor

| Part | Notes | Price | Link |
| --- | --- | ---: | --- |
| NEMA 17 stepper, bipolar | Belt drive. | $12 | [Amazon B00PNEQI7W](https://www.amazon.com/dp/B00PNEQI7W) |
| GT2 timing belt, 6 mm, plus 20T pulley | | in stock | n/a |
| Rollers / guide rods | 3D printed or aluminium, to keep envelopes square on the belt. | printed | n/a |
| DRV8825 stepper driver | | in stock | n/a |
| Buck converter, 12 V to 5 V | Logic rail off the motor supply. | in stock | n/a |

**Purchased total: $71.**

## AS5048A to AS5600 substitution

The BOM above specifies the **AS5048A**, a 14-bit SPI magnetic encoder on an adapter
board. The machine that was actually built runs an **AS5600**, a 12-bit I2C encoder, and
that is why the code reads the way it does:

- `src/hardware/as5600_encoder.py` and `src/hardware/rotbin_encoder.py` talk **I2C on
  bus 1**, not SPI. There is no chip-select line and no SPI bring-up anywhere in the
  hardware layer.
- Angle comes back as a **12-bit** raw count (0-4095, ~0.088° per LSB) rather than the
  AS5048A's 14-bit count. Bin slots are 60° apart, so 12 bits is far more resolution
  than the mechanism needs; the limit on landing accuracy is stepper overshoot, not
  encoder counts.
- The AS5600's I2C interface meant no extra SPI pins had to be freed on an already
  crowded header, and the breakout was a drop-in for the printed encoder mount.

The 8 mm x 3 mm diametric magnet in the BOM carries over unchanged; both parts want the
same diametrically magnetised disc centred on the shaft under the sensor.
