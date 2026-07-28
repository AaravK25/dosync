"""
schedule_client.py
------------------
Drop-in replacement for the `obtain_timings(path)` file-read in inference.py.

Import and use
--------------
    from schedule_client import obtain_timings

    # Fetch live from the Flask server (blocks until available or timeout):
    times = obtain_timings()

    # Optional: fall back to a local file if the server is unreachable:
    times = obtain_timings(fallback_path="schedule.json")

The function returns the same dict[str, datetime.time] that the original
`obtain_timings(path)` returned, so no other changes are needed in inference.py.
"""

import json
import urllib.request
import urllib.error
from datetime import time as dtime
from typing import Optional
import time as time_mod

SCHEDULE_URL = "http://127.0.0.1:5500/schedule"
_REQUIRED_KEYS = ("breakfast", "lunch", "dinner", "bed")


def _parse_time(s: str) -> dtime:
    h, m = map(int, s.split(":"))
    return dtime(h, m)


def _fetch_from_server(url: str, timeout: float) -> Optional[dict]:
    """
    Try to GET the schedule from the Flask server.
    Returns the parsed schedule dict on success, None on any error.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            body = json.loads(resp.read().decode())
            if body.get("ok") and "schedule" in body:
                return body["schedule"]
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        pass
    return None


def _fetch_from_file(path: str) -> dict:
    """Read schedule from a local JSON file (original behaviour)."""
    with open(path) as f:
        return json.load(f)


def obtain_timings(
    fallback_path: Optional[str] = None,
    server_url: str = SCHEDULE_URL,
    timeout: float = 5.0,
    poll_interval: float = 2.0,
    poll_attempts: int = 1,
) -> dict[str, dtime]:
    """
    Fetch the meal/bed schedule and return it as a dict of datetime.time objects.

    Parameters
    ----------
    fallback_path   : If given and the server is unreachable, read from this
                      local JSON file instead (preserves old behaviour).
    server_url      : URL of the Flask /schedule endpoint.
    timeout         : Per-attempt HTTP timeout in seconds.
    poll_interval   : Seconds to wait between retry attempts.
    poll_attempts   : How many times to try the server before giving up /
                      falling back. Set >1 to wait for the user to submit
                      the schedule from the HTML page.

    Returns
    -------
    dict mapping key → datetime.time, e.g.
        {"breakfast": time(8, 0), "lunch": time(13, 0), ...}

    Raises
    ------
    RuntimeError    : If the server is unreachable AND no fallback is given.
    FileNotFoundError / json.JSONDecodeError : propagated from fallback read.
    """
    raw: Optional[dict] = None

    for attempt in range(1, poll_attempts + 1):
        raw = _fetch_from_server(server_url, timeout)
        if raw is not None:
            break
        if attempt < poll_attempts:
            print(
                f"[schedule_client] Server not ready (attempt {attempt}/{poll_attempts}), "
                f"retrying in {poll_interval}s…"
            )
            time_mod.sleep(poll_interval)

    if raw is None:
        if fallback_path:
            print(
                f"[schedule_client] Flask server unreachable — "
                f"falling back to local file: {fallback_path!r}"
            )
            raw = _fetch_from_file(fallback_path)
        else:
            raise RuntimeError(
                f"[schedule_client] Could not fetch schedule from {server_url}. "
                "Make sure schedule_server.py is running and a schedule has been "
                "submitted from the Daily Rhythm page."
            )

    times = {k: _parse_time(raw[k]) for k in _REQUIRED_KEYS}
    print(f"[schedule_client] Schedule loaded: { {k: str(v) for k, v in times.items()} }")
    return times
