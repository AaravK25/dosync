import time
import serial
import serial.tools.list_ports

SERIAL_PORT = "COM6"        
BAUD_RATE   = 115200        
HOLD_SECS   = 2             


SERVO_MAP = {
    "a": "Sinarest  (servo 0)",
    "b": "Meftal    (servo 1)",
    "c": "Allegra   (servo 2)",
    "d": "Lanzol    (servo 3)",
}

def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports detected.")
        return
    print("\nAvailable serial ports:")
    for p in ports:
        print(f"  {p.device}  —  {p.description}")


def send(ser, ch):
    ser.write(ch.encode("ascii"))
    ser.flush()
    print(f"  >> sent '{ch}'")


def test_servo(ser, letter):
    """Activate one servo (lowercase) then reset it (uppercase)."""
    label = SERVO_MAP.get(letter.lower(), "unknown")
    print(f"\n[TEST] {label}")
    send(ser, letter.lower())          # dispense position (120°)
    time.sleep(HOLD_SECS)
    send(ser, letter.upper())          # rest position (90°)
    time.sleep(0.5)


def interactive_menu(ser):
    print("\n--- Interactive mode ---")
    print("Type a letter to test a servo, or 'q' to quit:")
    print("  a = Sinarest  |  A = reset Sinarest")
    print("  b = Meftal    |  B = reset Meftal")
    print("  c = Allegra   |  C = reset Allegra")
    print("  d = Lanzol    |  D = reset Lanzol")
    print("  r = run full cycle through all 4 servos")
    print("  q = quit")

    while True:
        cmd = input("\nCommand: ").strip()
        if not cmd: 
            continue
        if cmd == "q":
            break
        if cmd == "r":
            print("\nRunning full cycle …")
            for letter in ["a", "b", "c", "d"]:
                test_servo(ser, letter)
            print("Full cycle done.")
        elif cmd in "abcdABCD":
            send(ser, cmd)
        else:
            print("  [!] Unknown command — use a/b/c/d, A/B/C/D, r, or q.")


def main():
    print("=== Arduino Servo Serial Test ===")
    list_ports()

    print(f"\nConnecting to {SERIAL_PORT} @ {BAUD_RATE} baud …")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    except serial.SerialException as e:
        print(f"\n[ERROR] Could not open port: {e}")
        print("Check SERIAL_PORT at the top of this file and try again.")
        return

    time.sleep(2)   # wait for Uno Q to finish its reset-on-connect
    print("Connected.\n")

    choice = input("Run quick automatic test through all 4 servos first? [y/n]: ").strip().lower()
    if choice == "y":
        print("\nRunning automatic cycle …")
        for letter in ["a", "b", "c", "d"]:
            test_servo(ser, letter)
        print("\nAutomatic cycle complete.")

    interactive_menu(ser)

    ser.close()
    print("Port closed. Goodbye.")


if __name__ == "__main__":
    main()