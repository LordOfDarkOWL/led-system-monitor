#!/usr/bin/env python3
# LED Matrix System Monitor - Framework Laptop 16
#
# Linkes Modul (user view, Spalten 1-9):
#   Spalte 1: CPU frei    | Spalte 2: GPU frei (NVIDIA) | Spalte 3: CPU TEMP
#   Spalte 4: RAM frei    | Spalte 5: VRAM frei (NVIDIA)
#   Spalte 6: GPU TEMP
#   (Zeiger von unten: CPU 30-100C, GPU 30-85C)
#   Spalten 7-9: AKKU-ZELLEN (3x34=102 LEDs)
#     Start unten rechts (Spalte 9), pro Reihe rechts->links, Reihen unten->oben.
#     <=90%: 1% = genau 1 Zelle. >90%: 12 Zellen fuer 10% (bei 100% alle 102).
#   CPU/RAM-Balken von der Oberkante.
#
# Rechtes Modul:
#   Spalten 1-5: Downstream (1 Spalte = 1000Mbit%, 100er, 10er, 1er Stelle, kbit%) von oben
#   Spalte 6: Luecke
#   Spalten 7-9: Upstream (%, Einer Mbit, kbit%) von unten
#
# Panel-Kalibrierung: angezeigt[i] = gesendet[(i-1) mod 9]
#   => gesendet[k] = gewuenscht[(k+1) mod 9]
#
# Refresh: 10 Hz (Netzwerk/Helligkeit/rechts), 1 Hz (System/links), Akku 5s
# Auto-Helligkeit: IIO-Lichtsensor, EMA-geglättet, Dunkel=8, hell=255
import struct, subprocess, time, os

W, H = 9, 34
BMP_PATH = '/tmp/ledsysmon.bmp'
MIN_BRIGHT = 8       # Helligkeit (0-255) bei Dunkelheit, user-kalibriert
FADE_STEP = H / 20.0  # 1.7 px/Frame @10Hz -> volle Balken faded in ~2s aus


def read_cpu(prev):
    with open('/proc/stat') as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + parts[4]  # idle + iowait
    total = sum(parts)
    if prev is None:
        return None, (idle, total)
    didle = idle - prev[0]
    dtotal = total - prev[1]
    if dtotal <= 0:
        return None, (idle, total)
    return 100.0 * didle / dtotal, (idle, total)  # freie CPU %


def read_ram():
    info = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':')[0], int(line.split()[1])
            info[k] = v
    return 100.0 * info['MemAvailable'] / info['MemTotal']  # freie RAM %


def read_gpu():
    # (util %, used MiB, total MiB, temp C) via nvidia-smi
    try:
        out = subprocess.run(['nvidia-smi',
                              '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                              '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        u, mu, mt, tp = [float(x) for x in out.split(',')]
        return u, mu, mt, tp
    except Exception:
        return None


def read_cpu_temp():
    # CPU via acpitz thermal_zone3 (reagiert am schnellsten auf CPU-Last)
    try:
        return int(open('/sys/class/thermal/thermal_zone3/temp').read()) / 1000.0
    except Exception:
        return None


def read_battery():
    try:
        with open('/sys/class/power_supply/BAT1/capacity') as f:
            return float(f.read().strip())
    except OSError:
        return 0.0


def read_charge_status():
    # 'Charging' | 'Discharging' | 'Full' | 'Not charging' | 'Unknown'
    try:
        return open('/sys/class/power_supply/BAT1/status').read().strip()
    except Exception:
        return 'Unknown'


def battery_col_sets(cells):
    # gibt 3 Mengen physischer Reihen zurueck (Spalten-Indizes 6,7,8)
    # Fuellen: unten rechts zuerst, pro Reihe rechts->links, Reihen aufsteigend
    cols = [set(), set(), set()]
    for c in range(cells):
        row_from_bottom = c // 3
        offset = c % 3
        col_idx = 8 - offset            # 8,7,6
        phys_row = H - 1 - row_from_bottom
        cols[col_idx - 6].add(phys_row)
    return cols


def read_als():
    # Umgebungslicht (lux) vom IIO-Sensor; -1 wenn nicht lesbar
    try:
        d = '/sys/bus/iio/devices/iio:device0'
        raw = int(open(f'{d}/in_illuminance_raw').read())
        scale = float(open(f'{d}/in_illuminance_scale').read())
        return raw * scale
    except Exception:
        return -1.0


def ambient_brightness(lux, current_smoothed):
    # Dunkel (<10lx) -> MIN_BRIGHT (8 = user-kalibriert), ab ca. 500lx -> 255
    target = max(MIN_BRIGHT, min(255, int(round(8 + (lux - 10) * 0.5))))
    if lux < 0:
        return current_smoothed
    # EMA-Smoothing gegen Flackern (vorbeiziehende Hand etc.)
    # Alpha 0.1 bei 10 Hz -> Einschwingszeit ~2-3s
    return int(round(0.9 * current_smoothed + 0.1 * target))


def battery_cells(pct):
    # <=90%: 1% = 1 Zelle; >90%: 12 Zellen fuer 10% -> bei 100% alle 102
    pct = max(0.0, min(100.0, pct))
    if pct <= 90.0:
        return int(round(pct))
    return int(round(90.0 + (pct - 90.0) * 1.2))


def top_fill(fill):
    # phys rows 0..fill-1 (Oberkante)
    return set(range(fill))


def bottom_fill(fill):
    # phys rows H-fill..H-1
    return set(range(H - fill, H))


def empty():
    return set()


def build_bmp(col_rows):
    # col_rows: 9 Mengen von physischen Reihen (phys_row 0 = Oberkante)
    data = bytearray()
    for file_row in range(H):          # BMP bottom-up: file_row 0 = physisch unten
        phys_row = H - 1 - file_row
        for col in range(W):
            v = b'\xFF\xFF\xFF' if phys_row in col_rows[col] else b'\x00\x00\x00'
            data.extend(v)
        data.extend(b'\x00' * ((4 - (W * 3) % 4) % 4))  # padding
    bmp_size = 14 + 40 + len(data)
    header = b'BM' + struct.pack('<I', bmp_size) + b'\x00\x00\x00\x00' + struct.pack('<I', 54)
    info = (struct.pack('<I', 40) + struct.pack('<i', W) + struct.pack('<i', H)
            + struct.pack('<H', 1) + struct.pack('<H', 24) + struct.pack('<i', 0)
            + struct.pack('<I', len(data)) + struct.pack('<i', 2835) + struct.pack('<i', 2835)
            + struct.pack('<I', 0) + struct.pack('<I', 0) + struct.pack('<I', 0))
    return header + info + data


def read_net():
    rx = tx = 0
    base = '/sys/class/net'
    for iface in os.listdir(base):
        if iface == 'lo':
            continue
        try:
            with open(f'{base}/{iface}/statistics/rx_bytes') as f:
                rx += int(f.read())
            with open(f'{base}/{iface}/statistics/tx_bytes') as f:
                tx += int(f.read())
        except OSError:
            pass
    return rx, tx


RX_MAX_MBIT = 1000.0   # 1 Gbit/s
TX_MAX_MBIT = 50.0     # 50 Mbit/s


def pct(v):
    # Fuellhoehe (0..H) fuer Anteil v (0.0..1.0)
    return int(round(H * max(0.0, min(1.0, v))))


def digit_fill(val):
    # Ziffern-Encoding: voller Balken = 9.99
    return int(round(H * max(0.0, min(1.0, val / 9.99))))


def encode_speed(mbit, max_mbit):
    # [prozent_max, hunderter+dez, zehner+dez, einer+dez, kbit_anteil]
    s = min(mbit, 999.99)
    i = int(s)
    h, t, u = i // 100, (i // 10) % 10, i % 10
    frac = s - i
    return [
        pct(mbit / max_mbit),
        digit_fill(h + t / 10),
        digit_fill(t + u / 10),
        digit_fill(u + int(frac * 10) / 10),
        pct(frac),
    ]


def shift(desired):
    # gesendet[k] = gewuenscht[(k+1) mod 9]
    return [desired[(k + 1) % 9] for k in range(9)]


def send(dev, col_rows):
    bmp = build_bmp(col_rows)
    with open(BMP_PATH, 'wb') as f:
        f.write(bmp)
    subprocess.run(['inputmodule-control_cli_linux', '--serial-dev', dev,
                    'led-matrix', '--image-bw', BMP_PATH], capture_output=True)


def set_brightness(dev, val):
    subprocess.run(['inputmodule-control_cli_linux', '--serial-dev', dev,
                    'led-matrix', '--brightness', str(val)], capture_output=True)


def main():
    # 10 Hz Hauptloop: Netzwerk + Helligkeit + beide Module
    # 1 Hz: CPU/RAM/GPU/VRAM/Temp; Akku alle 5s
    # Lade-Animation: Pfeil laeuft von oben durch die Akku-Zellen
    cpu_prev = None
    cpu_free = 100.0
    ram_free = read_ram()
    gpu_f, vram_f = H, H
    cpu_temp = 30.0
    gpu_temp = 30.0
    batt = read_battery()
    cpu_f, ram_f = int(H * 0.99), int(H * 0.95)
    cpu_tmp_px = gpu_tmp_px = 0
    bat_cols_cached = battery_col_sets(battery_cells(batt))
    net_prev = None
    disp_h = [0.0] * 9        # aktuelle (gefadete) Balkhoehen rechtes Modul
    bright = MIN_BRIGHT
    last_sent_bright = -1
    t_last_slow = 0.0
    t_last_batt = 0.0
    arrow_y = None            # None = Animation inaktiv
    one_shot = False          # letzter Durchlauf nach Ladeende
    charging_prev = False
    snake_phase = 0           # 0 = auffuellen, 1 = ausfaden
    snake_idx = -1

    while True:
        t0 = time.monotonic()

        # --- Netzwerk-Rate (10 Hz, instant; Fade erfolgt auf Balkenkohe) ---
        rx, tx = read_net()
        rx_inst = tx_inst = 0.0
        if net_prev is not None:
            prx, ptx, pt = net_prev
            dt = t0 - pt
            if dt > 0:
                rx_inst = (rx - prx) * 8 / dt / 1e6
                tx_inst = (tx - ptx) * 8 / dt / 1e6
        net_prev = (rx, tx, t0)

        # --- Helligkeit (Sensor 10 Hz, EMA, nur bei Änderung >=2 senden) ---
        lux = read_als()
        bright = ambient_brightness(lux, bright)
        if abs(bright - last_sent_bright) >= 2:
            for dev in ('/dev/ttyACM0', '/dev/ttyACM1'):
                set_brightness(dev, bright)
            last_sent_bright = bright

        # --- Rechtes Modul: Netzwerk mit Fast-Attack / 2s Fade-out ---
        dn = encode_speed(rx_inst, RX_MAX_MBIT)
        up = encode_speed(tx_inst, TX_MAX_MBIT)
        if tx_inst < 10:
            up[1] = digit_fill(tx_inst)
        targets = [dn[0], dn[1], dn[2], dn[3], dn[4], 0,
                   up[0], up[1], up[4]]
        # Attack: sofort hoch; Release: linear FADE_STEP px/Frame -> 2s Fade
        for i in range(9):
            tgt = float(targets[i])
            if tgt >= disp_h[i]:
                disp_h[i] = tgt          # Zyklus-Reset bei neuem Traffic
            else:
                disp_h[i] = max(tgt, disp_h[i] - FADE_STEP)
        fills = [int(round(v)) for v in disp_h]
        right_desired = [top_fill(fills[0]), top_fill(fills[1]), top_fill(fills[2]),
                         top_fill(fills[3]), top_fill(fills[4]), empty(),
                         bottom_fill(fills[6]), bottom_fill(fills[7]), bottom_fill(fills[8])]
        send('/dev/ttyACM0', shift(right_desired))

        # --- 1 Hz: Systemwerte aktualisieren ---
        if t0 - t_last_slow >= 1.0:
            t_last_slow = t0
            cf, cpu_prev = read_cpu(cpu_prev)
            if cf is not None:
                cpu_free = cf
            ram_free = read_ram()
            gpu = read_gpu()
            if gpu is not None:
                util, mem_used, mem_total, gpu_temp = gpu
                gpu_f = int(round((100.0 - util) * H / 100))
                vram_f = int(round((mem_total - mem_used) * H / mem_total)) if mem_total else 0
            ct = read_cpu_temp()
            if ct is not None:
                cpu_temp = ct

            if t0 - t_last_batt >= 5.0:
                t_last_batt = t0
                batt = read_battery()
                bat_cols_cached = battery_col_sets(battery_cells(batt))

            cpu_f = int(round(cpu_free * H / 100))
            ram_f = int(round(ram_free * H / 100))
            # Thermometer-Zeiger von unten (full = 34 bei Max-Temp)
            cpu_tmp_px = int(round(H * max(0.0, min(1.0, (cpu_temp - 30.0) / (100.0 - 30.0)))))
            gpu_tmp_px = int(round(H * max(0.0, min(1.0, (gpu_temp - 30.0) / (85.0 - 30.0)))))

        # --- Lade-Status, Pfeil- & Snake-Animation ---
        status = read_charge_status()
        charging = status == 'Charging'
        idle_full = status in ('Full', 'Not charging')
        if charging:
            one_shot = True               # nach Ladeende: ein letzter Durchlauf
            if arrow_y is None:
                arrow_y = 0               # oben starten
            else:
                arrow_y += 1
                if arrow_y > H + 2:
                    arrow_y = 0           # loops, solange geladen wird
        elif one_shot and arrow_y is not None:
            arrow_y += 1
            if arrow_y > H + 2:
                one_shot = False
                arrow_y = None            # fertig, aus
        charging_prev = charging

        # --- Linkes Modul (10 Hz, wegen Animationen) ---
        if idle_full:
            # Snake-Sweep: alle 102 Zellen in Fuell-Reihenfolge
            # (unten rechts -> oben links) erst an-, dann wieder ausfaden
            snake_idx += 1
            if snake_phase == 0:
                if snake_idx > 101:
                    snake_phase, snake_idx = 1, -1     # alles an -> ausfaden
            else:
                if snake_idx > 101:
                    snake_phase, snake_idx = 0, -1     # alles aus -> neu starten
            bat_cols = [set(), set(), set()]
            for c in range(102):
                lit = (c <= snake_idx) if snake_phase == 0 else (c > snake_idx)
                if lit:
                    row_from_bottom = c // 3
                    pos = c % 3
                    # Richtung wechselt je Reihe: gerade r->l, ungerade l->r
                    col_idx = (8 - pos) if (row_from_bottom % 2 == 0) else (6 + pos)
                    bat_cols[col_idx - 6].add(H - 1 - row_from_bottom)
        else:
            snake_phase, snake_idx = 0, -1
            bat_cols = [set(s) for s in bat_cols_cached]
        if arrow_y is not None:
            # Pfeil nach unten: Spitze (arrow_y) + Schaft hoch, Querholz oben
            if arrow_y < H:
                bat_cols[1].add(arrow_y)      # Spitze, mittlere Spalte
            for shaft in (arrow_y - 1, arrow_y - 2):
                if shaft >= 0:
                    bat_cols[1].add(shaft)    # Schaft mittig
            top_row = arrow_y - 3
            if top_row >= 0:
                for c in range(3):
                    bat_cols[c].add(top_row)  # Querholz (3 Spalten)
        left_desired = [top_fill(cpu_f), top_fill(gpu_f), bottom_fill(cpu_tmp_px),
                        top_fill(ram_f), top_fill(vram_f), bottom_fill(gpu_tmp_px),
                        bat_cols[0], bat_cols[1], bat_cols[2]]
        send('/dev/ttyACM1', shift(left_desired))

        elapsed = time.monotonic() - t0
        time.sleep(max(0.01, 0.1 - elapsed))


if __name__ == '__main__':
    main()
