# LED Matrix System Monitor

**Echtzeit-System-Monitoring auf zwei LED-Matrix-Panelen für den [Framework Laptop 16](https://frame.work/laptops/laptop-16).**

## Über dieses Projekt

Dieses Projekt visualisiert Systemmetriken in Echtzeit auf zwei nebeneinander montierten LED-Panelen (je 9×34 LEDs). Der Monitor zeigt:

**Linkes Panel (System):**
- CPU-Auslastung (Balk)
- GPU-Auslastung (NVIDIA)
- CPU-Temperatur (Zeiger, 30–100 °C)
- RAM-Freier Speicher (Balk)
- VRAM-Freier Speicher (NVIDIA)
- Akku-Zellen (3×34=102 LEDs, Snake-Sweep-Animation beim Ladezustand)

**Rechtes Panel (Netzwerk):**
- Download-Rate (spaltenbasiert: %, 1000er, 100er, 10er, 1er, kbit)
- Upload-Rate (spaltenbasiert: %, 1000er, kbit)

### Besonderheiten

- **Auto-Helligkeit**: IIO-Umgebungslichtsensor (EMA geglättet, 8–255)
- **Lade-Animation**: Pfeil läuft durch Akku-Zellen, Snake-Sweep bei voller Ladung
- **Fade-Effekte**: Balken faden mit 10 Hz sanft ein/aus (~2 s)
- **Panel-Kalibrierung**: Kommt mit Shift-Matrix für korrekte physische Zuordnung

## Installation

### Voraussetzungen

- Linux (getestet auf Arch Linux)
- Python 3.10+
- NVIDIA GPU mit `nvidia-smi` (optional, für GPU/VRAM-Metriken)
- `inputmodule-control_cli_linux` (für das Ansteuern der LED-Module via UART)

### Schritte

```bash
git clone https://github.com/LordOfDarkOWL/led-system-monitor.git
cd led-system-monitor
pip install -r requirements.txt  # ggf. nur stdlib
chmod +x led-system-monitor.py
sudo ./led-system-monitor.py
```

> **Hinweis:** Das Skript benötigt `sudo`/Root für den Zugriff auf `/proc` und die seriellen Geräte (`/dev/ttyACM0`, `/dev/ttyACM1`).

## Panel-Konfiguration

Die Panels müssen physisch nebeneinander montiert werden (links = System, rechts = Netzwerk). Die `shift()`-Funktion in `led-system-monitor.py` berücksichtigt die physische LED-Adressierung.

### Helligkeit kalibrieren

Editiere in `led-system-monitor.py`:

```python
MIN_BRIGHT = 8  # Minimum-Helligkeit bei Dunkelheit (0–255)
```

## Architektur

```
led-system-monitor.py
├── read_cpu()        → /proc/stat
├── read_ram()        → /proc/meminfo
├── read_gpu()        → nvidia-smi
├── read_cpu_temp()   → /sys/class/thermal/thermal_zone3
├── read_battery()    → /sys/class/power_supply/BAT1
├── read_als()        → /sys/bus/iio/devices/iio:device0
├── read_net()        → /sys/class/net/*/statistics
├── build_bmp()       → 24-Bit BMP-Generator
├── send()            → inputmodule-control_cli_linux
└── main()            → 10 Hz Hauptloop
```

## Lizenz

MIT License – siehe [LICENSE](LICENSE).

---

> **Hintergrund:** Der Beispielcode stammt aus der Framework Laptop 16-Community. Dieses Projekt erweitert ihn um ein vollständiges System-Monitoring.
