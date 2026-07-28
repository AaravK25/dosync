"""
main.py
-------
Entry point for Dosync.

IMPORTANT — this is a different flow than before: schedule_server.py is a
long-running Flask server (it never exits on its own), so it can no longer
be one step in a sequential subprocess.run(...) chain — that would just
hang forever on step 1 and never reach inference.py.

Instead, schedule_server.py now stays running in the background and
auto-launches the rest of the pipeline (inference.py, then
reminder_system.py) itself, the moment a schedule is submitted from the
Daily Rhythm page. So all main.py needs to do is start that server and
keep it alive.

Usage
-----
    python main.py

Then:
    1. Open meal-timing.html in your browser.
    2. Fill in breakfast / lunch / dinner / bed times.
    3. Click "Start Dosync".

That single click POSTs your schedule to the server AND kicks off:
    inference.py        (captures + reads the prescription, saves output.json)
    reminder_system.py   (runs forever, dispensing doses on schedule)

Leave this terminal window open the whole time — closing it stops the
server, which stops everything downstream of it too.
"""

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
    print()
    print("Once it's running:")
    print("  1. Open meal-timing.html in your browser")
    print("  2. Fill in your breakfast / lunch / dinner / bed times")
    print("  3. Click 'Start Dosync'")
    print()
    print("That click automatically saves your schedule and runs the full")
    print("pipeline (inference.py -> reminder_system.py) for you.")
    print()
    print("Keep this window open — closing it stops everything.")
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
