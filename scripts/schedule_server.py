"""
schedule_server.py
------------------
Lightweight Flask bridge between the Daily Rhythm HTML page and inference.py.

Endpoints
---------
POST /schedule   - HTML page sends the schedule JSON here (replaces the
                   "download schedule.json" button).
GET  /schedule   - inference.py (via schedule_client.py) reads the latest
                   schedule from here.
GET  /status     - quick health-check / last-received timestamp.

Run
---
    python schedule_server.py

Server listens on http://127.0.0.1:5050 by default.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)  # allow the HTML page (file:// or any local origin) to POST here

# In-memory store — persists for the lifetime of the server process.
_schedule: dict | None = None
_last_updated: str | None = None

REQUIRED_KEYS = {"breakfast", "lunch", "dinner", "bed"}


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


@app.post("/schedule")
def receive_schedule():
    """Accept the schedule posted by the HTML page."""
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
    return jsonify({"ok": True, "schedule": _schedule, "updated": _last_updated}), 200


@app.get("/schedule")
def serve_schedule():
    """Return the latest schedule to inference.py (or any other consumer)."""
    if _schedule is None:
        return jsonify({"ok": False, "error": "No schedule has been submitted yet."}), 404
    return jsonify({"ok": True, "schedule": _schedule, "updated": _last_updated}), 200


@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "schedule_present": _schedule is not None,
        "last_updated": _last_updated,
    }), 200


if __name__ == "__main__":
    print("Daily Rhythm schedule server running on http://127.0.0.1:5050")
    print("  POST /schedule  ← HTML page sends schedule here")
    print("  GET  /schedule  ← inference.py reads schedule from here")
    app.run(host="127.0.0.1", port=5500, debug=False)
