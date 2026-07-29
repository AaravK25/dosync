import json
import time
import threading
from datetime import datetime

import serial
import serial.tools.list_ports

SERIAL_PORT = "COM6"         
BAUD_RATE = 115200            
OUTPUT_JSON_PATH = "output.json"

ACTIVATE_HOLD_SECONDS = 3     
CHECK_INTERVAL_SECONDS = 20   
STAGGER_SECONDS = 1           #gap between servos if two doses land at once


MEDICINE_SERVO_MAP = {
    "sinarest": {"on": "c", "off": "C"},
    "meftal":   {"on": "b", "off": "B"},
    "lanzol":   {"on": "d", "off": "D"},
}

_ser_lock = threading.Lock()



def list_serial_ports():
    """Print available serial ports, handy for finding the Uno Q's COM port."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}  -  {p.description}")


def load_prescriptions(path=OUTPUT_JSON_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def match_servo(medicine_name):
    """Case-insensitive match of a prescription's medicine name to a known servo."""
    if not medicine_name:
        return None
    name = medicine_name.strip().lower()
    for key, letters in MEDICINE_SERVO_MAP.items():
        if key in name or name in key:
            return key, letters
    return None


def _normalize_time(t):
    """Accept 'HH:MM' or 'HHMM' and return 'HH:MM'."""
    digits = t.replace(":", "").strip()
    if len(digits) != 4 or not digits.isdigit():
        return None
    return f"{digits[:2]}:{digits[2:]}"


def build_reminder_table(prescriptions):
    """
    Turns the prescription list into: {"HH:MM": [(medicine_name, letters), ...]}
    Medicines that aren't one of the 4 known ones are skipped (nothing to
    actuate for them) and reported so you notice.
    """
    table = {}
    for entry in prescriptions:
        medicine = entry.get("medicine")
        timing = entry.get("timing")
        if not medicine or not timing:
            continue

        matched = match_servo(medicine)
        if matched is None:
            print(f"[warn] '{medicine}' isn't one of the 4 known medicines — skipping (no servo assigned).")
            continue
        known_name, letters = matched

        for raw_t in timing:
            t = _normalize_time(str(raw_t))
            if t is None:
                print(f"[warn] Unrecognized time '{raw_t}' for {medicine} — skipping that entry.")
                continue
            table.setdefault(t, []).append((medicine, known_name, letters))

    return table


def send_char(ser, ch):
    with _ser_lock:
        ser.write(ch.encode("ascii"))
        ser.flush()
    print(f"[serial] sent '{ch}'")


def trigger_dose(ser, medicine, letters):
    print(f"[reminder] Time to take {medicine}!")
    send_char(ser, letters["on"])
    time.sleep(ACTIVATE_HOLD_SECONDS)
    send_char(ser, letters["off"])



def run_scheduler(reminder_table, port=SERIAL_PORT, baud=BAUD_RATE):
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)  # let the Uno Q finish its reset-on-connect before we send anything

    print("\nScheduled doses:")
    for t, meds in sorted(reminder_table.items()):
        names = ", ".join(f"{m} ({k})" for m, k, _ in meds)
        print(f"  {t} -> {names}")
    print("\nReminder scheduler running. Ctrl+C to stop.\n")

    fired_today = set()
    last_day = datetime.now().date()

    try:
        while True:
            now = datetime.now()
            if now.date() != last_day:
                fired_today.clear()
                last_day = now.date()

            current_hm = now.strftime("%H:%M")
            if current_hm in reminder_table and current_hm not in fired_today:
                for medicine, _known_name, letters in reminder_table[current_hm]:
                    trigger_dose(ser, medicine, letters)
                    time.sleep(STAGGER_SECONDS)
                fired_today.add(current_hm)

            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping reminder scheduler.")
    finally:
        ser.close()


if __name__ == "__main__":
   

    prescriptions = load_prescriptions()
    reminder_table = build_reminder_table(prescriptions)

    if not reminder_table:
        print("No doses matched to a known medicine/servo — nothing to schedule.")
    else:
        run_scheduler(reminder_table)
