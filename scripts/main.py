import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_SERVER = os.path.join(SCRIPT_DIR, "schedule_server.py")


def main():
    print("=" * 60)
    print("Dosync")
    print("=" * 60)
    print("Starting the schedule bridge server...")
    print("pipeline (inference.py to reminder_system.py)")
    print()
    print("Keep window open - closing it stops all processes.")
    print("=" * 60)
    print()

    try:
        subprocess.run([sys.executable, SCHEDULE_SERVER], check=True, cwd=SCRIPT_DIR)
    except KeyboardInterrupt:
        print("\nStopped.")
    except subprocess.CalledProcessError as e:
        print(f"\nschedule_server.py exited with an error (code {e.returncode}).")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
