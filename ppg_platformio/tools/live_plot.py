#!/usr/bin/env python3
"""Live-plot the PPG waveform streamed over serial by ppg_platformio/src/main.cpp.

The firmware prints one raw ADC sample per line at ~250 Hz. This script reads
those lines and draws a scrolling line plot so you can eyeball waveform
quality (Phase 1 goal: confirm a clean pulse before committing to a PCB).

Usage:
    python3 live_plot.py --port /dev/ttyACM0
"""

import argparse
import collections
import sys
import threading
import time

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import serial


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--window", type=float, default=1.0, help="Seconds of history to display")
    parser.add_argument("--ymin", type=float, default=0, help="Fixed y-axis lower bound (ADC counts)")
    parser.add_argument("--ymax", type=float, default=1023, help="Fixed y-axis upper bound (ADC counts)")
    return parser.parse_args()


def read_serial(ser, times, values, lock, start_time, window):
    """Background thread: parse incoming lines, ignoring anything malformed.

    Times are stored modulo `window` so the plot sweeps a fixed x-axis
    (oscilloscope-style) instead of scrolling. Crossing back past zero means
    a new sweep has started, so the previous sweep's trace is cleared.
    """
    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
        except serial.SerialException:
            return
        if not line:
            continue
        try:
            value = int(line)
        except ValueError:
            continue
        x = (time.monotonic() - start_time) % window
        with lock:
            if times and x < times[-1]:
                times.clear()
                values.clear()
            times.append(x)
            values.append(value)


def main():
    args = parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print(f"Couldn't open {args.port}: {exc}", file=sys.stderr)
        sys.exit(1)

    times = collections.deque()
    values = collections.deque()
    lock = threading.Lock()
    start_time = time.monotonic()

    reader = threading.Thread(
        target=read_serial,
        args=(ser, times, values, lock, start_time, args.window),
        daemon=True,
    )
    reader.start()

    fig, ax = plt.subplots()
    (line,) = ax.plot([], [])
    ax.set_title("PPG signal")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("ADC counts")

    ax.set_xlim(0, args.window)
    ax.set_ylim(args.ymin, args.ymax)

    def update(_frame):
        with lock:
            xs = list(times)
            ys = list(values)

        if not xs:
            return (line,)

        line.set_data(xs, ys)
        return (line,)

    ani = animation.FuncAnimation(fig, update, interval=50, blit=False)
    try:
        plt.show()
    finally:
        ser.close()


if __name__ == "__main__":
    main()
