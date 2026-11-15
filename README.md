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
- `inputmodule-control_cli_linux` (for driving LED modules via UART)

### Steps

```bash
git clone https://github.com/LordOfDarkOWL/led-system-monitor.git
cd led-system-monitor
pip install -r requirements.txt  # stdlib only, no extra deps needed
chmod +x led-system-monitor.py
sudo ./led-system-monitor.py
```

> **Note:** The script requires `sudo`/root for access to `/proc` and serial devices (`/dev/ttyACM0`, `/dev/ttyACM1`).

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

## License

MIT License – see [LICENSE](LICENSE).

---

> **Background:** The example code originated from the Framework Laptop 16 community. This project extends it into a complete system monitoring solution.
