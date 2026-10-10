#!/usr/bin/env python3
"""Live-plot the PPG waveform streamed over serial by ppg_platformio/src/main.cpp.

The firmware prints one raw ADC sample per line at ~250 Hz. This script reads
those lines and draws a scrolling line plot so you can eyeball waveform
quality, plus a live FFT magnitude spectrum so you can confirm the heart-rate
tone and check the RC filter chain's frequency response against theory.

Usage:
    python3 tools/live_plot.py

The serial port is detected automatically and can be changed from the GUI.
Use --port only when you explicitly want to select a device at launch.
"""

import argparse
import collections
import threading
import time

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import serial
from matplotlib.widgets import Button, TextBox
from serial.tools import list_ports

# Physiological band used to pick the heart-rate peak out of the spectrum
# (0.5-3.5 Hz = 30-210 BPM), rather than a random low-frequency artifact.
HR_BAND_HZ = (0.5, 3.5)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        help="Serial port, e.g. /dev/ttyACM0 or COM3 (default: auto-detect)",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--window", type=float, default=1.0, help="Seconds of history to display in the waveform plot")
    parser.add_argument("--ymin", type=float, default=0, help="Fixed y-axis lower bound (ADC counts)")
    parser.add_argument("--ymax", type=float, default=1023, help="Fixed y-axis upper bound (ADC counts)")
    parser.add_argument("--fft-window", type=float, default=4.0, help="Seconds of history used for the FFT (longer = finer frequency resolution)")
    parser.add_argument("--sample-rate", type=float, default=250.0, help="Nominal firmware sample rate (Hz), used to size the FFT buffer")
    return parser.parse_args()


def read_serial(ser, times, values, fft_buf, lock, stop_event, start_time, window):
    """Background thread: parse incoming lines, ignoring anything malformed.

    `times`/`values` are stored modulo `window` so the waveform plot sweeps a
    fixed x-axis (oscilloscope-style) instead of scrolling. `fft_buf` holds
    the same samples in true chronological order (never wrapped) so the FFT
    sees a continuous signal rather than a sweep discontinuity.
    """
    while not stop_event.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
        except (OSError, TypeError, serial.SerialException):
            return
        if not line:
            continue
        try:
            value = int(line)
        except ValueError:
            continue
        now = time.monotonic()
        x = (now - start_time) % window
        with lock:
            if times and x < times[-1]:
                times.clear()
                values.clear()
            times.append(x)
            values.append(value)
            fft_buf.append((now, value))


def main():
    args = parse_args()

    times = collections.deque()
    values = collections.deque()
    fft_buf = collections.deque(maxlen=int(args.fft_window * args.sample_rate))
    lock = threading.Lock()
    fig, (ax, ax_fft) = plt.subplots(2, 1, figsize=(8, 7))
    (line,) = ax.plot([], [])
    ax.set_title("PPG signal")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("ADC counts")
    ax.set_xlim(0, args.window)
    ax.set_ylim(args.ymin, args.ymax)

    (spectrum_line,) = ax_fft.plot([], [])
    peak_marker = ax_fft.axvline(0, color="tab:red", linestyle="--", alpha=0, label="Heart-rate peak")
    peak_text = ax_fft.text(0.98, 0.80, "", transform=ax_fft.transAxes, ha="right", color="tab:red")
    ax_fft.set_title("Spectrum (FFT)")
    ax_fft.set_xlabel("Frequency (Hz)")
    ax_fft.set_ylabel("Magnitude")
    ax_fft.set_xlim(0, args.sample_rate / 2)
    ax_fft.legend(loc="upper right")
    fig.tight_layout(rect=(0, 0.11, 1, 1))

    detected_ports = [port.device for port in list_ports.comports()]
    initial_port = args.port or (detected_ports[0] if detected_ports else "")

    port_ax = fig.add_axes((0.10, 0.025, 0.34, 0.05))
    refresh_ax = fig.add_axes((0.46, 0.025, 0.10, 0.05))
    connect_ax = fig.add_axes((0.58, 0.025, 0.11, 0.05))
    port_box = TextBox(port_ax, "Port: ", initial=initial_port)
    refresh_button = Button(refresh_ax, "Refresh")
    connect_button = Button(connect_ax, "Connect")
    status_text = fig.text(0.71, 0.05, "", va="center", fontsize=9)

    serial_connection: serial.Serial | None = None
    reader_thread: threading.Thread | None = None
    reader_stop_event: threading.Event | None = None
    connected_port: str | None = None

    def set_status(message, color):
        status_text.set_text(message)
        status_text.set_color(color)
        fig.canvas.draw_idle()

    def disconnect():
        nonlocal serial_connection, reader_thread, reader_stop_event, connected_port

        if reader_stop_event is not None:
            reader_stop_event.set()
        if serial_connection is not None:
            try:
                serial_connection.close()
            except (OSError, serial.SerialException):
                pass
        if reader_thread is not None:
            reader_thread.join(timeout=1.1)

        serial_connection = None
        reader_thread = None
        reader_stop_event = None
        connected_port = None

    def connect(port):
        nonlocal serial_connection, reader_thread, reader_stop_event, connected_port

        port = port.strip()
        if not port:
            set_status("Enter a serial port", "tab:red")
            return
        if port == connected_port and serial_connection is not None:
            set_status(f"Connected to {port}", "tab:green")
            return

        try:
            new_ser = serial.Serial(port, args.baud, timeout=1)
        except (OSError, serial.SerialException) as exc:
            set_status(f"Couldn't open {port}: {exc}", "tab:red")
            return

        disconnect()
        with lock:
            times.clear()
            values.clear()
            fft_buf.clear()

        reader_stop_event = threading.Event()
        reader_thread = threading.Thread(
            target=read_serial,
            args=(
                new_ser,
                times,
                values,
                fft_buf,
                lock,
                reader_stop_event,
                time.monotonic(),
                args.window,
            ),
            daemon=True,
        )
        serial_connection = new_ser
        connected_port = port
        reader_thread.start()
        set_status(f"Connected to {port}", "tab:green")

    def refresh_ports(_event):
        ports = [port.device for port in list_ports.comports()]
        if not ports:
            set_status("No serial ports found", "tab:red")
            return

        selected_port = port_box.text if port_box.text in ports else ports[0]
        port_box.eventson = False
        port_box.set_val(selected_port)
        port_box.eventson = True
        connect(selected_port)

    port_box.on_submit(connect)
    refresh_button.on_clicked(refresh_ports)
    connect_button.on_clicked(lambda _event: connect(port_box.text))
    if initial_port:
        connect(initial_port)
    else:
        set_status("No serial ports found", "tab:red")

    def update(_frame):
        with lock:
            xs = list(times)
            ys = list(values)
            fft_samples = list(fft_buf)

        line.set_data(xs, ys)

        if len(fft_samples) >= 8:
            sample_times, sample_values = zip(*fft_samples)
            fs = (len(sample_times) - 1) / (sample_times[-1] - sample_times[0])

            # Hann window trims spectral leakage from the finite, non-periodic
            # sample block; removing the mean drops the DC bin that would
            # otherwise dwarf the heart-rate tone.
            detrended = np.array(sample_values) - np.mean(sample_values)
            windowed = detrended * np.hanning(len(detrended))
            mag = np.abs(np.fft.rfft(windowed))
            freqs = np.fft.rfftfreq(len(windowed), d=1 / fs)

            spectrum_line.set_data(freqs, mag)
            ax_fft.set_xlim(0, fs / 2)
            ax_fft.set_ylim(0, max(mag.max(), 1) * 1.1)

            band = (freqs >= HR_BAND_HZ[0]) & (freqs <= HR_BAND_HZ[1])
            if band.any():
                peak_freq = freqs[band][np.argmax(mag[band])]
                peak_marker.set_xdata([peak_freq, peak_freq])
                peak_marker.set_alpha(0.8)
                peak_text.set_text(f"{peak_freq:.2f} Hz ({peak_freq * 60:.0f} BPM)")
        else:
            spectrum_line.set_data([], [])
            peak_marker.set_alpha(0)
            peak_text.set_text("")

        return (line, spectrum_line, peak_marker, peak_text)

    ani = animation.FuncAnimation(
        fig,
        update,
        interval=50,
        blit=False,
        cache_frame_data=False,
    )
    try:
        plt.show()
    finally:
        disconnect()


if __name__ == "__main__":
    main()
