#!/usr/bin/env python3
"""Replay a recorded PPG CSV over a virtual serial port, mimicking the firmware.

Creates a pseudo-terminal, prints its path, then streams one integer ADC sample
per line at --rate Hz (looping forever) so live_plot.py can be tested without
hardware. The source signal is resampled to --rate and scaled into 0-1023 to
match the Teensy's 10-bit ADC output.

Designed for the PhysioNet BIDMC CSVs (column " PLETH", 125 Hz), but any CSV
with a header row works via --column / --source-rate.

Usage:
    python3 replay_ppg.py bidmc_01_Signals.csv
    python3 live_plot.py --port /dev/pts/N      # path printed by this script
"""

import argparse
import csv
import os
import time
import tty

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="CSV file containing a PPG column")
    parser.add_argument("--column", default="PLETH", help="PPG column name (whitespace-insensitive)")
    parser.add_argument("--source-rate", type=float, default=125.0, help="Sample rate of the CSV (Hz)")
    parser.add_argument("--rate", type=float, default=250.0, help="Output sample rate (Hz), matching the firmware")
    return parser.parse_args()


def load_signal(path, column):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        idx = header.index(column)
        return np.array([float(row[idx]) for row in reader if row[idx].strip()])


def main():
    args = parse_args()
    signal = load_signal(args.csv, args.column)

    # Linear-interpolate onto the firmware's sample grid, then map the
    # recording's range onto the ADC's 10-bit range with a little headroom.
    t_src = np.arange(len(signal)) / args.source_rate
    t_out = np.arange(0, t_src[-1], 1 / args.rate)
    resampled = np.interp(t_out, t_src, signal)
    lo, hi = resampled.min(), resampled.max()
    adc = np.round(100 + (resampled - lo) / (hi - lo) * 800).astype(int)

    master, slave = os.openpty()
    tty.setraw(slave)
    print(f"Streaming {len(adc) / args.rate:.0f} s of PPG at {args.rate:.0f} Hz (looping)", flush=True)
    print(f"Run: python3 live_plot.py --port {os.ttyname(slave)}", flush=True)

    period = 1 / args.rate
    next_t = time.monotonic()
    try:
        while True:
            for value in adc:
                os.write(master, f"{value}\r\n".encode())
                next_t += period
                delay = next_t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
