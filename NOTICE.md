# Third-party notices

## dewenni/ESP32-Jarolift-Controller
<https://github.com/dewenni/ESP32-Jarolift-Controller> — MIT License, Copyright (c) 2024 Sven T.

- `custom_components/jarolift_rf/core/` re-implements in Python the telegram layout, timing and
  command sequences of `lib/JaroliftController` (v1.9.0).
- `tests/reference/upstream/` contains unmodified copies of `JaroliftController.{cpp,h}` and
  `KeeloqLib.{cpp,h}` with the original license (`tests/reference/upstream/LICENSE`), used only to
  generate test vectors.

## KeeloqLib (Frank Kienast, 2010)
KeeLoq implementation shipped with the project above; ported to Python in
`custom_components/jarolift_rf/core/keeloq.py`.

## KeeLoq
KeeLoq is a technology of Microchip Technology Inc. This project contains no manufacturer keys.
It is intended for private use with your own devices only.
