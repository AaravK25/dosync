import subprocess
import sys
print("starting schedule_server.py...")
subprocess.run([sys.executable, "d:/Codes/dosync/scripts/schedule_server.py"], check=True)

print("starting schedule_client.py..")
subprocess.run([sys.executable, "d:/Codes/dosync/scripts/schedule_client.py"], check=True)

print("Starting inference.py...")
subprocess.run([sys.executable, "d:/Codes/dosync/scripts/inference.py"], check=True)

print("inference done...")

print("Starting reminder_system.py...")
subprocess.run([sys.executable, "d:/Codes/dosync/scripts/reminder_system.py"], check=True)


print("Both scripts have finished executing!")
