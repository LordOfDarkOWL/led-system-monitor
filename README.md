# LED Matrix System Monitor

**Real-time system monitoring on two LED-matrix panels for the [Framework Laptop 16](https://frame.work/laptops/laptop-16).**

## About

This project displays system metrics in real-time on two side-by-side LED panels (each 9×34 LEDs). The monitor shows:

**Left Panel (System):**
- CPU usage (bar)
- GPU usage (NVIDIA)
- CPU temperature (indicator, 30–100 °C)
- Free RAM (bar)
- Free VRAM (NVIDIA)
- Battery cells (3×34=102 LEDs, snake-sweep animation on charge state)

**Right Panel (Network):**
- Download rate (column-based: %, 1000s, 100s, 10s, 1s, kbit)
- Upload rate (column-based: %, 1000s, kbit)

### Features

- **Auto-brightness**: IIO ambient light sensor (EMA smoothed, 8–255)
- **Charge animation**: Arrow runs through battery cells, snake-sweep on full charge
- **Fade effects**: Bars fade in/out at 10 Hz (~2 s)
- **Panel calibration**: Includes shift matrix for correct physical addressing

## Installation

### Prerequisites

- Linux (tested on Arch Linux)
- Python 3.10+
- NVIDIA GPU with `nvidia-smi` (optional, for GPU/VRAM metrics)
- `inputmodule-control_cli_linux` (for driving LED modules via USB serial)
  - **Download**: [Framework Computer/inputmodule-rs Releases](https://github.com/FrameworkComputer/inputmodule-rs/releases) (v0.2.0 recommended)
  - Place in PATH (e.g., `/usr/local/bin/inputmodule-control_cli_linux`)

### Steps

```bash
git clone https://github.com/LordOfDarkOWL/led-system-monitor.git
cd led-system-monitor
pip install -r requirements.txt  # stdlib only, no extra deps needed
chmod +x led-system-monitor.py
sudo ./led-system-monitor.py
```

> **Note:** The script requires `sudo`/root for access to `/proc` and serial devices (`/dev/ttyACM0`, `/dev/ttyACM1`).
> **Reference**: The `inputmodule-control_cli_linux` binary is released at [FrameworkComputer/inputmodule-rs](https://github.com/FrameworkComputer/inputmodule-rs/releases). The LED panel hardware (9×34, RP2040 + IS31FL3741A) is documented in the [InputModules](https://github.com/FrameworkComputer/InputModules) repo.

## Panel Configuration

The panels must be mounted physically side-by-side (left = System, right = Network). The `shift()` function in `led-system-monitor.py` accounts for the physical LED addressing.

### Calibrate brightness

Edit in `led-system-monitor.py`:

```python
MIN_BRIGHT = 8  # Minimum brightness in darkness (0–255)
```

## Architecture

```
led-system-monitor.py
├── read_cpu()        → /proc/stat
├── read_ram()        → /proc/meminfo
├── read_gpu()        → nvidia-smi
├── read_cpu_temp()   → /sys/class/thermal/thermal_zone3
├── read_battery()    → /sys/class/power_supply/BAT1
├── read_als()        → /sys/bus/iio/devices/iio:device0
├── read_net()        → /sys/class/net/*/statistics
├── build_bmp()       → 24-bit BMP generator
├── send()            → inputmodule-control_cli_linux
└── main()            → 10 Hz main loop
```

## Related Framework Resources

- [FrameworkComputer/inputmodule-rs](https://github.com/FrameworkComputer/inputmodule-rs) – Official Input Module SW/FW (321 ⭐)
- [FrameworkComputer/InputModules](https://github.com/FrameworkComputer/InputModules) – Reference designs & docs (246 ⭐)
- [FrameworkComputer/dotmatrixtool](https://github.com/FrameworkComputer/dotmatrixtool) – Web tool for LED matrix BMP generation (31 ⭐)
- [FrameworkComputer/qmk_firmware](https://github.com/FrameworkComputer/qmk_firmware) – QMK fork for Framework 16

## License

MIT License

Copyright (c) 2025 LordOfDarkOWL

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
## Submitting to Framework

If you'd like this to be considered for the official Framework ecosystem, you can:
- Open a **Discussion** or **Issue** in [FrameworkComputer/InputModules](https://github.com/FrameworkComputer/InputModules) or [inputmodule-rs](https://github.com/FrameworkComputer/inputmodule-rs)
- Propose it as a community tool alongside the official ones

---

> **Background:** The example code originated from the Framework Laptop 16 community. This project extends it into a complete system monitoring solution.
