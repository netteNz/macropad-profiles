"""Print the MacroPad's serial output (print() lines, tracebacks).

    .venv\\Scripts\\python tools\\serial_console.py            # watch until Ctrl+C
    .venv\\Scripts\\python tools\\serial_console.py --reload   # restart code.py first
    .venv\\Scripts\\python tools\\serial_console.py --reload --seconds 8

--reload sends Ctrl+C then Ctrl+D (a soft reload), so code.py runs again from
the top and its boot lines (e.g. "panel: ...") show up. That interrupts the
pad and resets its screen. The port is found by Adafruit's USB vendor ID;
pass --port COMx to override.
"""
import argparse
import sys
import time

import serial
from serial.tools import list_ports

ADAFRUIT_VID = 0x239A


def find_port():
    for p in list_ports.comports():
        if p.vid == ADAFRUIT_VID:
            return p.device
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--reload", action="store_true", help="soft-reload code.py first")
    ap.add_argument("--seconds", type=float, help="stop after this long")
    args = ap.parse_args()
    # CircuitPython's banner has an emoji; Windows consoles default to cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    port = args.port or find_port()
    if not port:
        sys.exit("No CircuitPython board found (is the MacroPad plugged in?)")
    print("--- %s (Ctrl+C to quit) ---" % port, flush=True)

    with serial.Serial(port, 115200, timeout=0.1) as s:
        if args.reload:
            s.write(b"\x03")  # Ctrl+C: stop code.py
            time.sleep(0.3)
            s.write(b"\x04")  # Ctrl+D: soft reload, runs code.py again
        end = time.monotonic() + args.seconds if args.seconds else None
        try:
            while end is None or time.monotonic() < end:
                data = s.read(512)
                if data:
                    sys.stdout.write(data.decode("utf-8", "replace"))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            pass
    print("\n--- closed ---")


if __name__ == "__main__":
    main()
