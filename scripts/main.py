import subprocess
import sys

print("Starting inference.py...")
subprocess.run([sys.executable, "inference.py"], check=True)

print("Starting reminder_system.py...")
subprocess.run([sys.executable, "reminder_system.py"], check=True)

print("Both scripts have finished executing!")
