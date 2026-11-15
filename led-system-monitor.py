#!/usr/bin/env python3
# LED Matrix System Monitor - Framework Laptop 16
#
# Left panel (user view, columns 1-9):
#   Col 1: Free CPU    | Col 2: Free GPU (NVIDIA) | Col 3: CPU TEMP
#   Col 4: Free RAM   | Col 5: Free VRAM (NVIDIA)
#   Col 6: GPU TEMP
#   (Indicators from bottom: CPU 30-100C, GPU 30-85C)
#   Cols 7-9: BATTERY CELLS (3x34=102 LEDs)
#     Start bottom-right (col 9), row right->left, rows bottom->top.
#     <=90%: 1% = exactly 1 cell. >90%: 12 cells per 10% (100% = all 102).
#   CPU/RAM bars from the top edge.
#
# Right panel:
#   Cols 1-5: Download (1 col = 1000Mbit%, 100s, 10s, 1s, kbit%) from top
#   Col 6: Gap
#   Cols 7-9: Upload (%, 1000s Mbit, kbit%) from bottom
#
# Panel calibration: displayed[i] = sent[(i-1) mod 9]
#   => sent[k] = desired[(k+1) mod 9]
#
# Refresh: 10 Hz (network/brightness/right), 1 Hz (system/left), battery 5s
# Auto-brightness: IIO light sensor, EMA-smoothed, dark=8, bright=255
import struct, subprocess, time, os

W, H = 9, 34
BMP_PATH = '/tmp/ledsysmon.bmp'
MIN_BRIGHT = 8       # Brightness (0-255) in darkness, user-calibrated
FADE_STEP = H / 20.0  # 1.7 px/frame @10Hz -> full bars fade out in ~2s


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
    return 100.0 * didle / dtotal, (idle, total)  # free CPU %


def read_ram():
    info = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':')[0], int(line.split()[1])
            info[k] = v
    return 100.0 * info['MemAvailable'] / info['MemTotal']  # free RAM %


def read_gpu():
    # (util %, used MiB, total MiB, temp °C) via nvidia-smi
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
    # CPU temp via acpitz thermal_zone3 (fastest responding to CPU load)
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
    # returns 3 sets of physical rows (col indices 6,7,8)
    # Fill: bottom-right first, per row right->left, rows ascending
    cols = [set(), set(), set()]
    for c in range(cells):
        row_from_bottom = c // 3
        offset = c % 3
        col_idx = 8 - offset            # 8,7,6
        phys_row = H - 1 - row_from_bottom
        cols[col_idx - 6].add(phys_row)
    return cols


def read_als():
    # Ambient light (lux) from IIO sensor; -1 if unreadable
    try:
        d = '/sys/bus/iio/devices/iio:device0'
        raw = int(open(f'{d}/in_illuminance_raw').read())
        scale = float(open(f'{d}/in_illuminance_scale').read())
        return raw * scale
    except Exception:
        return -1.0


def ambient_brightness(lux, current_smoothed):
    # Dark (<10lx) -> MIN_BRIGHT (8 = user-calibrated), ~500lx -> 255
    target = max(MIN_BRIGHT, min(255, int(round(8 + (lux - 10) * 0.5))))
    if lux < 0:
        return current_smoothed
    # EMA smoothing against flicker (passing hand etc.)
    # Alpha 0.1 at 10 Hz -> settling time ~2-3s
    return int(round(0.9 * current_smoothed + 0.1 * target))


def battery_cells(pct):
    # <=90%: 1% = 1 cell; >90%: 12 cells for 10% -> at 100% all 102
    pct = max(0.0, min(100.0, pct))
    if pct <= 90.0:
        return int(round(pct))
    return int(round(90.0 + (pct - 90.0) * 1.2))


def top_fill(fill):
    # physical rows 0..fill-1 (top edge)
    return set(range(fill))


def bottom_fill(fill):
    # phys rows H-fill..H-1
    return set(range(H - fill, H))


def empty():
    return set()


def build_bmp(col_rows):
    # col_rows: 9 sets of physical rows (phys_row 0 = top edge)
    data = bytearray()
    for file_row in range(H):          # BMP bottom-up: file_row 0 = physically bottom
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
    # Fill height (0..H) for fraction v (0.0..1.0)
    return int(round(H * max(0.0, min(1.0, v))))


def digit_fill(val):
    # Digit encoding: full bar = 9.99
    return int(round(H * max(0.0, min(1.0, val / 9.99))))


def encode_speed(mbit, max_mbit):
    # [pct_max, hundreds+dec, tens+dec, ones+dec, kbit_fraction]
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
    # sent[k] = desired[(k+1) mod 9]
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
    # 10 Hz main loop: network + brightness + both modules
    # 1 Hz: CPU/RAM/GPU/VRAM/temp; battery every 5s
    # Charge animation: arrow runs from top through battery cells
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
    disp_h = [0.0] * 9        # current (faded) bar heights, right module
    bright = MIN_BRIGHT
    last_sent_bright = -1
    t_last_slow = 0.0
    t_last_batt = 0.0
    arrow_y = None            # None = animation inactive
    arrow_dir = 1             # 1 = down (charge), -1 = up (discharge)
    one_shot = False          # final pass after charging ends
    charging_prev = False
    snake_phase = 0           # 0 = fill, 1 = fade out
    snake_idx = -1
    discharge_phase = 0       # 0 = empty (drain), 1 = refill (reverse snake)
    discharge_idx = -1        # discharge animation counter (0-101)

    while True:
        t0 = time.monotonic()

        # --- Network rate (10 Hz, instant; fade on bar height) ---
        rx, tx = read_net()
        rx_inst = tx_inst = 0.0
        if net_prev is not None:
            prx, ptx, pt = net_prev
            dt = t0 - pt
            if dt > 0:
                rx_inst = (rx - prx) * 8 / dt / 1e6
                tx_inst = (tx - ptx) * 8 / dt / 1e6
        net_prev = (rx, tx, t0)

        # --- Brightness (sensor 10 Hz, EMA, send only on change >=2) ---
        lux = read_als()
        bright = ambient_brightness(lux, bright)
        if abs(bright - last_sent_bright) >= 2:
            for dev in ('/dev/ttyACM0', '/dev/ttyACM1'):
                set_brightness(dev, bright)
            last_sent_bright = bright

        # --- Right module: network with fast-attack / 2s fade-out ---
        dn = encode_speed(rx_inst, RX_MAX_MBIT)
        up = encode_speed(tx_inst, TX_MAX_MBIT)
        if tx_inst < 10:
            up[1] = digit_fill(tx_inst)
        targets = [dn[0], dn[1], dn[2], dn[3], dn[4], 0,
                   up[0], up[1], up[4]]
        # Attack: instant up; Release: linear FADE_STEP px/frame -> 2s fade
        for i in range(9):
            tgt = float(targets[i])
            if tgt >= disp_h[i]:
                disp_h[i] = tgt          # cycle reset on new traffic
            else:
                disp_h[i] = max(tgt, disp_h[i] - FADE_STEP)
        fills = [int(round(v)) for v in disp_h]
        right_desired = [top_fill(fills[0]), top_fill(fills[1]), top_fill(fills[2]),
                         top_fill(fills[3]), top_fill(fills[4]), empty(),
                         bottom_fill(fills[6]), bottom_fill(fills[7]), bottom_fill(fills[8])]
        send('/dev/ttyACM0', shift(right_desired))

        # --- 1 Hz: update system values ---
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
            # Thermometer indicator from bottom (full = 34 at max temp)
            cpu_tmp_px = int(round(H * max(0.0, min(1.0, (cpu_temp - 30.0) / (100.0 - 30.0)))))
            gpu_tmp_px = int(round(H * max(0.0, min(1.0, (gpu_temp - 30.0) / (85.0 - 30.0)))))

        # --- Charge status, arrow & snake animation ---
        status = read_charge_status()
        charging = status == 'Charging'
        idle_full = batt >= 99.5 and status in ('Full', 'Not charging')  # actual 100% + idle
        discharging = not charging and not idle_full and batt < 99.5

        # Charging: arrow runs top->bottom, loops; one_shot at end
        if charging:
            one_shot = True               # after charging ends: one final pass
            if arrow_y is None:
                arrow_y = 0               # start from top
            else:
                arrow_y += 1
                if arrow_y > H + 2:
                    arrow_y = 0           # loops while charging
        elif one_shot and arrow_y is not None:
            arrow_y += 1
            if arrow_y > H + 2:
                one_shot = False
                arrow_y = None            # done, off
        charging_prev = charging

        # --- Discharge: arrow runs bottom->top (reversed charge arrow) ---
        if discharging:
            if arrow_y is None:
                arrow_y = H + 2           # start from bottom (above panel)
            else:
                arrow_y -= 1              # move up
            if arrow_y < -2:
                arrow_y = H + 2           # loops while discharging
        elif one_shot and arrow_y is not None:
            arrow_y += 1
            if arrow_y > H + 2:
                one_shot = False
                arrow_y = None            # done, off

        # --- Left module (10 Hz, for animations) ---
        if idle_full:
            # Snake-sweep: all 102 cells in fill order
            # (bottom-right -> top-left) first fill, then fade out
            snake_idx += 1
            if snake_phase == 0:
                if snake_idx > 101:
                    snake_phase, snake_idx = 1, -1     # all on -> fade out
            else:
                if snake_idx > 101:
                    snake_phase, snake_idx = 0, -1     # all off -> restart
            bat_cols = [set(), set(), set()]
            for c in range(102):
                lit = (c <= snake_idx) if snake_phase == 0 else (c > snake_idx)
                if lit:
                    row_from_bottom = c // 3
                    pos = c % 3
                    # Direction alternates per row: even r->l, odd l->r
                    col_idx = (8 - pos) if (row_from_bottom % 2 == 0) else (6 + pos)
                    bat_cols[col_idx - 6].add(H - 1 - row_from_bottom)
        elif discharging:
            # Discharge: show battery cells + upward arrow
            bat_cols = [set(s) for s in bat_cols_cached]
        else:
            snake_phase, snake_idx = 0, -1
            bat_cols = [set(s) for s in bat_cols_cached]
        if arrow_y is not None:
            # Upward arrow (discharge): tip (arrow_y) + shaft down, crossbar below
            # Downward arrow (charge): tip (arrow_y) + shaft up, crossbar above
            if arrow_dir == -1:
                # Up: tip at arrow_y, shaft below, crossbar 3 rows below
                if arrow_y >= 0:
                    bat_cols[1].add(arrow_y)      # tip, middle column
                for shaft in (arrow_y + 1, arrow_y + 2):
                    if shaft < H:
                        bat_cols[1].add(shaft)    # shaft centered
                bot_row = arrow_y + 3
                if bot_row < H:
                    for c in range(3):
                        bat_cols[c].add(bot_row)  # crossbar (3 cols)
            else:
                # Up arrow (charge): tip at bottom, shaft up, crossbar at top
                if arrow_y >= 0:
                    bat_cols[1].add(arrow_y)      # tip, bottom of arrow
                for shaft in (arrow_y - 1, arrow_y - 2):
                    if shaft >= 0:
                        bat_cols[1].add(shaft)    # shaft centered above tip
                top_row = arrow_y - 3
                if top_row >= 0:
                    for c in range(3):
                        bat_cols[c].add(top_row)  # crossbar at top of arrow
        left_desired = [top_fill(cpu_f), top_fill(gpu_f), bottom_fill(cpu_tmp_px),
                        top_fill(ram_f), top_fill(vram_f), bottom_fill(gpu_tmp_px),
                        bat_cols[0], bat_cols[1], bat_cols[2]]
        send('/dev/ttyACM1', shift(left_desired))

        elapsed = time.monotonic() - t0
        time.sleep(max(0.01, 0.1 - elapsed))


if __name__ == '__main__':
    main()
