"""
schedule_server.py
------------------
Lightweight Flask bridge between the Daily Rhythm HTML page and the rest of
the Dosync pipeline (inference.py -> reminder_system.py).

Endpoints
---------
POST /schedule          - HTML page sends the schedule JSON here. On success
                          this ALSO kicks off the Dosync pipeline in the
                          background:
                              1. inference.py         (OCR + medicine extraction,
                                                        runs to completion)
                              2. reminder_system.py    (dose monitor/dispenser,
                                                        runs indefinitely)
GET  /schedule           - inference.py (via schedule_client.py) reads the
                          latest schedule from here.
GET  /pipeline-status    - Poll this to see what the pipeline is doing right
                          now: idle / running_inference / monitoring / error.
GET  /status             - quick health-check / last-received timestamp.

Run
---
    python schedule_server.py

Server listens on http://127.0.0.1:5500 by default.

Notes
-----
- inference.py and reminder_system.py are launched using the SAME Python
  interpreter that is running this server (sys.executable), and with this
  script's own folder as both the working directory and script location —
  so they must live alongside schedule_server.py, exactly as in this repo.
- reminder_system.py runs forever (it's a dose scheduler loop), so it is
  started with subprocess.Popen (fire-and-forget) rather than
  subprocess.run. A background watcher thread tracks its exit in case it
  ever crashes, so /pipeline-status can report that accurately.
- Only one pipeline run is allowed at a time. If a schedule is submitted
  while inference is still running, or while the reminder daemon is
  already monitoring doses, the schedule is still saved but a NEW pipeline
  run is NOT started (the response says so). Restart the server to run the
  pipeline again from a clean state.
"""

import os
import sys
import threading
import subprocess
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # allow the HTML page (file:// or any local origin) to POST here

# ---------------------------------------------------------------------------
# Schedule state
# ---------------------------------------------------------------------------

_schedule: dict | None = None
_last_updated: str | None = None

REQUIRED_KEYS = {"breakfast", "lunch", "dinner", "bed"}

# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INFERENCE_SCRIPT = os.path.join(SCRIPT_DIR, "inference.py")
REMINDER_SCRIPT = os.path.join(SCRIPT_DIR, "reminder_system.py")

_pipeline_lock = threading.Lock()
_pipeline_state = {
    "status": "idle",       # idle | running_inference | monitoring | error
    "stage": None,          # human-readable description of current stage
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _set_pipeline_state(**kwargs):
    with _pipeline_lock:
        _pipeline_state.update(kwargs)


def _pipeline_snapshot():
    with _pipeline_lock:
        return dict(_pipeline_state)


def _launch_reminder_daemon():
    """Start reminder_system.py as a background daemon (it runs forever)."""
    print("[schedule_server] Launching reminder_system.py (daemon)...")
    proc = subprocess.Popen(
        [sys.executable, REMINDER_SCRIPT],
        cwd=SCRIPT_DIR,
    )

    def _watch():
        returncode = proc.wait()
        with _pipeline_lock:
            # Only report a crash if we were still expecting this daemon to
            # be running (avoids clobbering a later, intentional restart).
            if _pipeline_state["status"] == "monitoring":
                if returncode != 0:
                    _pipeline_state.update({
                        "status": "error",
                        "error": f"reminder_system.py exited unexpectedly (code {returncode}).",
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                    })
                else:
                    _pipeline_state.update({
                        "status": "idle",
                        "stage": None,
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                    })
        print(f"[schedule_server] reminder_system.py exited (code {returncode}).")

    threading.Thread(target=_watch, daemon=True).start()


def _run_pipeline_worker():
    _set_pipeline_state(
        status="running_inference",
        stage="inference.py (capturing + reading prescription)",
        error=None,
        started_at=datetime.now().isoformat(timespec="seconds"),
        finished_at=None,
    )
    try:
        print("[schedule_server] Launching inference.py ...")
        subprocess.run(
            [sys.executable, INFERENCE_SCRIPT],
            check=True,
            cwd=SCRIPT_DIR,
        )
        print("[schedule_server] inference.py finished successfully.")

        _set_pipeline_state(stage="reminder_system.py (starting dose monitor)")
        _launch_reminder_daemon()

        _set_pipeline_state(
            status="monitoring",
            stage="reminder_system.py (monitoring + dispensing doses)",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        print("[schedule_server] Dosync is live and monitoring doses.")

    except subprocess.CalledProcessError as e:
        script_name = os.path.basename(e.cmd[-1]) if isinstance(e.cmd, list) else str(e.cmd)
        _set_pipeline_state(
            status="error",
            error=f"{script_name} exited with code {e.returncode}.",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        print(f"[schedule_server] Pipeline failed: {e}")
    except Exception as e:
        _set_pipeline_state(
            status="error",
            error=str(e),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        print(f"[schedule_server] Pipeline failed: {e}")


def start_pipeline_if_idle() -> bool:
    """
    Kick off the pipeline in a background thread if nothing is currently
    running. Returns True if a new run was started, False if the pipeline
    was already active (running_inference or monitoring).
    """
    with _pipeline_lock:
        if _pipeline_state["status"] in ("running_inference", "monitoring"):
            return False
    threading.Thread(target=_run_pipeline_worker, daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Schedule validation
# ---------------------------------------------------------------------------

def _validate(data: dict) -> str | None:
    """Return an error string, or None if data is valid."""
    if not isinstance(data, dict):
        return "Payload must be a JSON object."
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        return f"Missing keys: {', '.join(sorted(missing))}"
    for key in REQUIRED_KEYS:
        val = data[key]
        if not isinstance(val, str):
            return f"Value for '{key}' must be a string."
        parts = val.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            return f"Value for '{key}' must be HH:MM, got: {val!r}"
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return f"Value for '{key}' is out of range: {val!r}"
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/schedule")
def receive_schedule():
    """Accept the schedule posted by the HTML page, then auto-start Dosync."""
    global _schedule, _last_updated

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"ok": False, "error": "No valid JSON body received."}), 400

    err = _validate(data)
    if err:
        return jsonify({"ok": False, "error": err}), 422

    _schedule = {k: data[k] for k in REQUIRED_KEYS}
    _last_updated = datetime.now().isoformat(timespec="seconds")
    print(f"[schedule_server] Schedule received at {_last_updated}: {_schedule}")

    started = start_pipeline_if_idle()
    pipeline = _pipeline_snapshot()

    if started:
        message = "Schedule saved. Dosync pipeline started."
    elif pipeline["status"] == "running_inference":
        message = "Schedule saved, but Dosync is already reading a prescription. Please wait for it to finish."
    else:  # monitoring
        message = "Schedule saved, but Dosync is already monitoring doses. Restart the server to run the pipeline again with this new schedule."

    return jsonify({
        "ok": True,
        "schedule": _schedule,
        "updated": _last_updated,
        "pipeline_started": started,
        "pipeline": pipeline,
        "message": message,
    }), 200


@app.get("/schedule")
def serve_schedule():
    """Return the latest schedule to inference.py (or any other consumer)."""
    if _schedule is None:
        return jsonify({"ok": False, "error": "No schedule has been submitted yet."}), 404
    return jsonify({"ok": True, "schedule": _schedule, "updated": _last_updated}), 200


@app.get("/pipeline-status")
def pipeline_status():
    return jsonify({"ok": True, "pipeline": _pipeline_snapshot()}), 200


@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "schedule_present": _schedule is not None,
        "last_updated": _last_updated,
        "pipeline": _pipeline_snapshot(),
    }), 200


if __name__ == "__main__":
    print("Daily Rhythm / Dosync bridge server running on http://127.0.0.1:5500")
    print("  POST /schedule         <- HTML page sends schedule here (also starts the pipeline)")
    print("  GET  /schedule         <- inference.py reads schedule from here")
    print("  GET  /pipeline-status  <- poll for pipeline progress")
    print(f"  Pipeline scripts expected in: {SCRIPT_DIR}")
    # threaded=True so status polls are served promptly while the pipeline
    # runs in its own background thread.
    app.run(host="127.0.0.1", port=5500, debug=False, threaded=True)
