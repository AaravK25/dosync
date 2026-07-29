import os
import openai
import base64
import cv2 as cv
import time as time_mod          

import subprocess
import urllib.request
import urllib.error
import atexit
import json


SERVER_DIR = r"C:\AI-CUDA\llama.cpp\build\bin\Release"
SERVER_EXE = "llama-server.exe"
SERVER_PATH = os.path.join(SERVER_DIR, SERVER_EXE)

PADDLE_CMD = [
    SERVER_PATH,
    "-m", r"C:\AI-CUDA\llama.cpp\models\PaddleOCR-VL-1.6-GGUF.gguf",
    "--mmproj", r"C:\AI-CUDA\llama.cpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf",
    "-ngl", "999",
    "-c", "32000",
    "--cache-type-k", "q8_0",
    "--alias", "paddleocr",
    "--port", "8080",
    "-fa", "auto",
    "-t", "6",
]

QWEN_CMD = [
    SERVER_PATH,
    "-m", r"C:\AI-CUDA\llama.cpp\models\Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
    "-ngl", "999",
    "-c", "32000",
    "--cache-type-k", "q8_0",
    "--alias", "qwen3",
    "--port", "8081",
    "-fa", "on",
    "-t", "6",
]

_server_procs = []


def start_server(cmd, name):
    print(f"Starting {name} server...")
    proc = subprocess.Popen(
        cmd,
        cwd=SERVER_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW,  
    )
    _server_procs.append(proc)
    return proc


def wait_for_server(port, name, timeout=120):
    url = f"http://127.0.0.1:{port}"
    start = time_mod.time()
    while time_mod.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    print(f"{name} server is ready on port {port}.")
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time_mod.sleep(1)
    raise TimeoutError(f"{name} server did not become ready on port {port} within {timeout}s")


def shutdown_servers():
    for proc in _server_procs:
        if proc.poll() is None:
            proc.terminate()


def startnstop_servers():
    atexit.register(shutdown_servers)

    start_server(PADDLE_CMD, "PaddleOCR")
    start_server(QWEN_CMD, "Qwen3-VL")

    wait_for_server(8080, "PaddleOCR")
    wait_for_server(8081, "Qwen3-VL")


def capture_encode_pic():

    vid = cv.VideoCapture(1)

    for i in range(3):
        return_value, image = vid.read()
        cv.imwrite('opencv' + str(i) + '.jpg', image)
    del (vid)
    image_path = r"opencv1"
    time_mod.sleep(1.2)
    with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode().strip()


from schedule_client import obtain_timings  

paddle = openai.OpenAI(
    base_url="http://127.0.0.1:8080",
    api_key="sk_no_api_key_required"
)

qwen = openai.OpenAI(
    base_url="http://127.0.0.1:8081",
    api_key="sk_no_api_key_required"
)

def ocr_extract():
    ocr = paddle.responses.create(
        model="Paddle-VL-0.9b",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url" : capture_encode_pic()
                    }
                ]
            }
        ]
    )

    text = ocr.output_text
    print("ocr done")
    return text

def json_extract(text):
    """
    IMPORTANT DESIGN NOTE:
    The model does NOT compute clock times anymore. Small VL models (e.g. the
    2B Qwen model used here) are unreliable at multi-step time arithmetic and
    at actually using numbers supplied in a long instruction block — in
    testing it was ignoring the real schedule and outputting generic times
    like 08:00/13:00/23:00 regardless of what the person entered.

    Instead, the model only does what it's good at: reading messy OCR text
    and classifying each dose as an (anchor, direction, offset_minutes)
    triple, e.g. "30 min after lunch" -> anchor="lunch", direction="after",
    offset_minutes=30. The actual HH:MM clock time is then computed
    deterministically in Python (see resolve_dose_timings below), using the
    real schedule fetched from obtain_timings(). This guarantees the final
    timing always matches what the person entered on the Daily Rhythm page.
    """
    response = qwen.responses.create(
        model="Qwen3-vl-2b-UD-Q4_K_XL",
        max_output_tokens=512,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"""You are a medical prescription tag extractor. You receive raw OCR text extracted 
                        from a handwritten or printed prescription image by PaddleOCR-VL. This text may 
                        contain spelling errors, missing spaces, broken words, or OCR noise. Your job is 
                        to identify every medicine mentioned and extract fields for each — but you must
                        NOT do any clock-time math yourself. Just classify each dose relative to the
                        person's daily anchors (breakfast / lunch / dinner / bed); a separate program
                        will convert that into real clock times.

                        1. medicine — the medicine/drug name, corrected to its standard/generic or brand 
                        spelling if the OCR text is a clear misspelling. If unreadable or ambiguous, 
                        output "UNKNOWN".
                        2. frequency — number of times the medicine is to be taken per day, as an integer 
                        (e.g. 1, 2, 3). Convert common shorthand:
                        - OD / once daily → 1
                        - BD / BID → 2
                        - TDS / TID → 3
                        - QID → 4
                        - SOS / PRN (as needed) → 0
                        If not mentioned, output null.
                        3. doses — a JSON array with one object PER DOSE (the array length MUST equal
                        frequency, unless frequency is 0/null/unclear, in which case output an empty
                        array [] and let the fallback defaults apply). Each dose object has exactly:
                            - "anchor": one of "breakfast", "lunch", "dinner", "bed"
                            - "direction": one of "before", "after", "at"
                            - "offset_minutes": a non-negative integer (0 if direction is "at")
                        Mapping rules from the prescription's wording to anchor/direction/offset:
                        - "30 min after lunch" → anchor="lunch", direction="after", offset_minutes=30
                        - "before dinner" → anchor="dinner", direction="before", offset_minutes=30 (default offset when unspecified)
                        - "1 hour after breakfast" → anchor="breakfast", direction="after", offset_minutes=60
                        - "at bedtime" / "HS" → anchor="bed", direction="at", offset_minutes=0
                        - "with lunch" / "at lunch" → anchor="lunch", direction="at", offset_minutes=0
                        - Generic labels with no explicit meal/offset reference map to the nearest anchor,
                        direction="at", offset_minutes=0:
                          morning → breakfast · afternoon → lunch · evening → dinner · night → dinner
                        - If the prescription gives NO usable timing info at all for a dose, omit that
                        dose from the array (do not guess arbitrary anchors).
                        - Do not invent an anchor/offset that isn't supported by the text.

                        SAME MEDICINE AT DIFFERENT TIMES:
                        If a medicine appears multiple times in the prescription with different timings 
                        or doses (e.g. "Metformin 500mg morning, Metformin 1000mg night"), create a 
                        SEPARATE object for each entry, with a "note" field describing the distinction 
                        (e.g. dose strength, condition). If there is no distinguishing note, still 
                        create separate objects — do not merge them.

                        STRICT OUTPUT RULES:
                        - Output ONLY a JSON array. No explanations, no preamble, no markdown, no extra text.
                        - One object per medicine entry, in the order they appear in the input.
                        - Use exactly these keys: "medicine", "frequency", "doses", and optionally "note".
                        - "doses" must always be a JSON array of objects (possibly empty []), never a string.
                        - If the OCR text contains no identifiable medicines, output: []
                        - Do not invent medicines that aren't in the text.
                        - Do not include dosage strength (mg/ml), doctor name, patient name, or duration 
                        (days/weeks) in the medicine field — only the fields above.
                        - Never output a clock time (HH:MM) anywhere. Only anchor/direction/offset_minutes.

                        OUTPUT FORMAT EXAMPLE (THIS IS JUST AN EXAMPLE):
                        [
                            {{"medicine": "Paracetamol", "frequency": 2, "doses": [
                                {{"anchor": "breakfast", "direction": "at", "offset_minutes": 0}},
                                {{"anchor": "dinner", "direction": "after", "offset_minutes": 30}}
                            ]}},
                            {{"medicine": "Azithromycin", "frequency": 1, "doses": [
                                {{"anchor": "breakfast", "direction": "at", "offset_minutes": 0}}
                            ]}}
                        ]

                        Now process the following OCR text and return only the JSON array:

                        {text}"""
                    }
                ]
            }
        ]
    )

    json_array = response.output_text
    return json_array




_DEFAULT_DOSE_PLANS = {
    1: [("breakfast", "at", 0)],
    2: [("breakfast", "at", 0), ("dinner", "at", 0)],
    3: [("breakfast", "at", 0), ("lunch", "at", 0), ("dinner", "at", 0)],
    4: [("breakfast", "at", 0), ("lunch", "at", 0), ("dinner", "at", 0), ("bed", "at", 0)],
}


def _resolve_single_time(schedule, anchor, direction, offset_minutes):
    anchor_time = schedule.get(anchor)
    if anchor_time is None:
        return None
    base_minutes = anchor_time.hour * 60 + anchor_time.minute
    offset_minutes = int(offset_minutes or 0)
    if direction == "before":
        total = base_minutes - offset_minutes
    elif direction == "after":
        total = base_minutes + offset_minutes
    else:  # "at"
        total = base_minutes
    total %= 1440  # roll over correctly across midnight
    h, m = divmod(total, 60)
    return f"{h:02d}:{m:02d}"


def resolve_dose_timings(prescriptions, schedule):
    """
    Takes the model's output (medicine/frequency/doses[]) and the REAL
    schedule from obtain_timings(), and produces the final medicine list
    with a computed "timing" field — matching the shape reminder_system.py
    expects: {"medicine", "frequency", "timing", "note"?}.
    """
    resolved = []
    for entry in prescriptions:
        medicine = entry.get("medicine")
        frequency = entry.get("frequency")
        doses = entry.get("doses") or []

        if not doses and frequency in _DEFAULT_DOSE_PLANS:
            doses = [
                {"anchor": a, "direction": d, "offset_minutes": o}
                for a, d, o in _DEFAULT_DOSE_PLANS[frequency]
            ]

        timing = []
        for dose in doses:
            t = _resolve_single_time(
                schedule,
                dose.get("anchor"),
                dose.get("direction", "at"),
                dose.get("offset_minutes", 0),
            )
            if t:
                timing.append(t)

        out_entry = {
            "medicine": medicine,
            "frequency": frequency,
            "timing": timing,
        }
        if "note" in entry:
            out_entry["note"] = entry["note"]
        resolved.append(out_entry)

    return resolved


def _clean_json_text(raw):
    """Strip markdown code fences etc. in case the model adds them despite instructions."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


if __name__ == "__main__":
    startnstop_servers()

    ocr_text = ocr_extract()
    raw_output = json_extract(ocr_text)

    try:
        model_prescriptions = json.loads(_clean_json_text(raw_output))
    except json.JSONDecodeError as e:
        print(f"[warn] Could not parse model output as JSON: {e}")
        model_prescriptions = []

    schedule = obtain_timings()
    print(f"[inference] Using schedule: { {k: v.strftime('%H:%M') for k, v in schedule.items()} }")

    parsed_prescriptions = resolve_dose_timings(model_prescriptions, schedule)

    with open("output.json", "w", encoding="utf-8") as file:
        json.dump(parsed_prescriptions, file, indent=4)

    print(f"Saved {len(parsed_prescriptions)} medicine entr{'y' if len(parsed_prescriptions)==1 else 'ies'} to output.json")
    for p in parsed_prescriptions:
        print(f"  {p['medicine']}: {p['timing']}")