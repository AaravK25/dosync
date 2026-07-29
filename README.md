# Dosync

Dosync reads a handwritten or printed prescription from a photo, works out when
each medicine should be taken based on your own daily meal/sleep schedule, and
automatically dispenses doses at the right time using an Arduino-driven servo
system.

## How it works

The pipeline has four stages, wired together by a small local Flask server:

1. **Daily Rhythm (`meal-timing.html`)** - a web page where you enter your
   breakfast, lunch, dinner, and bed times. Submitting the form POSTs the
   schedule to the local server and kicks off the rest of the pipeline.

2. **Schedule bridge (`schedule_server.py` / `schedule_client.py`)** - a Flask
   server that stores the schedule you submitted and serves it back to the
   rest of the pipeline. It also tracks pipeline status (idle, running
   inference, monitoring, error) so the web page can show live progress.

3. **Prescription reading (`inference.py`)** - captures/loads a prescription
   image, runs it through a local PaddleOCR-VL model to extract raw text,
   then runs that text through a local Qwen3-VL model to identify each
   medicine, its frequency, and when each dose should be taken relative to
   your meals (for example, "30 minutes after lunch"). The actual clock time
   for each dose is then calculated in plain Python using your real schedule,
   not by the language model, so the result always matches what you entered
   on the Daily Rhythm page. The result is saved to `output.json`.

4. **Dose reminders (`reminder_system.py`)** - reads `output.json`, builds a
   daily dose table, and runs indefinitely, sending single-character
   commands over a serial connection to an Arduino Uno Q at each scheduled
   time. The Arduino swings the matching servo to dispense the dose, then
   returns it to rest.

## Requirements

- Python 3.11 (or compatible)
- `llama-server.exe` from llama.cpp, with the following local models:
  - PaddleOCR-VL-1.6-GGUF (plus its mmproj file)
  - Qwen3-VL-2B-Instruct-UD-Q4_K_XL
- Python packages: `openai`, `opencv-python`, `flask`, `flask-cors`,
  `pyserial`
- An Arduino Uno Q (or compatible board) running a sketch that listens for
  the single-character servo commands described below
- A webcam or a saved prescription image

Install the Python dependencies:

```
pip install openai opencv-python flask flask-cors pyserial
```

## Setup

1. Update the model and server paths in `inference.py` (`SERVER_DIR`,
   `SERVER_PATH`, and the `-m` / `--mmproj` paths in `PADDLE_CMD` and
   `QWEN_CMD`) to match where llama.cpp and the GGUF models are installed on
   your machine.

2. Update `capture_encode_pic()` in `inference.py` to either capture from
   your webcam or point at the prescription image you want to process.

3. In `reminder_system.py`, set `SERIAL_PORT` to the COM port (Windows) or
   device path (Linux/Mac) your Arduino is connected to. Run
   `list_serial_ports()` from that file if you are not sure which port to
   use.

4. In `reminder_system.py`, update `MEDICINE_SERVO_MAP` so the medicine
   names you expect map to the correct servo channel. Matching is
   case-insensitive and uses substring matching, so the medicine name
   extracted from the prescription only needs to contain (or be contained
   in) one of the keys you list here. Any medicine that does not match one
   of these keys is skipped, since there is no servo assigned to it.

## Running

1. Start the pipeline:

   ```
   python main.py
   ```

   This starts `schedule_server.py` on `http://127.0.0.1:5500` and keeps it
   running. Leave this terminal window open for the entire session; closing
   it stops the server and everything downstream of it.

2. Open `meal-timing.html` in your browser.

3. Fill in your breakfast, lunch, dinner, and bed times.

4. Click "Start Dosync". This saves your schedule and automatically runs:

   - `inference.py` (captures and reads the prescription, saves
     `output.json`)
   - `reminder_system.py` (runs indefinitely, dispensing doses on schedule)

   The page polls `/pipeline-status` and shows live progress: reading the
   prescription, then "Dosync is live" once the reminder daemon is
   monitoring doses.

## Arduino protocol

`reminder_system.py` only ever sends eight single ASCII characters over
serial, one pair per servo channel:

| Character | Meaning                        |
|-----------|---------------------------------|
| `a`       | Swing servo 1 to dispense position |
| `A`       | Return servo 1 to rest position |
| `b`       | Swing servo 2 to dispense position |
| `B`       | Return servo 2 to rest position |
| `c`       | Swing servo 3 to dispense position |
| `C`       | Return servo 3 to rest position |
| `d`       | Swing servo 4 to dispense position |
| `D`       | Return servo 4 to rest position |

All servo motion, angles, and timing beyond the hold duration are handled on
the Arduino side.

## File overview

| File                  | Role                                                        |
|------------------------|--------------------------------------------------------------|
| `main.py`              | Entry point; starts the schedule bridge server and keeps it alive |
| `meal-timing.html`     | Daily Rhythm web page for entering your schedule              |
| `schedule_server.py`   | Flask server: stores the schedule, tracks pipeline status, launches inference and reminder stages |
| `schedule_client.py`   | Helper used by `inference.py` to fetch the current schedule from the server |
| `inference.py`         | OCR + medicine/timing extraction; writes `output.json`        |
| `reminder_system.py`   | Reads `output.json`, schedules doses, drives the Arduino over serial |

## Output format

`output.json` is a JSON array of medicine entries, for example:

```json
[
    {
        "medicine": "Paracetamol",
        "frequency": 2,
        "timing": ["08:00", "21:00"]
    },
    {
        "medicine": "Azithromycin",
        "frequency": 1,
        "timing": ["08:00"],
        "note": "500mg strength"
    }
]
```

`timing` entries are always in 24-hour `HH:MM` format, computed from your
submitted schedule rather than guessed by the language model.

## Troubleshooting

- **Schedule does not seem to be used**: check the terminal running
  `schedule_server.py`. It prints the schedule it received and, later, the
  schedule `inference.py` fetched and the final timing computed for each
  medicine. If those do not match what you entered, confirm you are running
  the latest `inference.py` and that the server was not left over from a
  previous run.

- **Servo never fires for a known medicine**: check the terminal running
  `reminder_system.py` for `[warn] '<medicine>' isn't one of the 4 known
  medicines` messages. This means the extracted medicine name did not match
  any key in `MEDICINE_SERVO_MAP`; update the map to include it.

- **"Could not reach server" in the browser**: make sure `main.py` is still
  running and that nothing else is bound to port 5500.

- **Pipeline stuck on "Schedule saved, but Dosync is already monitoring
  doses"**: only one pipeline run is allowed per server session. Stop and
  restart `main.py` to run the pipeline again with a new schedule.

## Notes

- `schedule_server.py` runs Flask's built-in development server, which is
  fine for local, single-user use but is not intended for production
  deployment.
- The reminder scheduler checks the clock every 20 seconds by default
  (`CHECK_INTERVAL_SECONDS` in `reminder_system.py`); doses are only fired
  once per scheduled minute per day.
