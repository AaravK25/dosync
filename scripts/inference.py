import os
import openai
import base64
import cv2 as cv
import time as time_mod          
from datetime import time as dtime  
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
        creationflags=subprocess.CREATE_NEW_CONSOLE,  
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

    vid = cv.VideoCapture(0)

    for i in range(3):
        return_value, image = vid.read()
        cv.imwrite('opencv' + str(i) + '.jpg', image)
    del (vid)
    image_path = r"opencv1.jpg"
    time_mod.sleep(1.2)
    with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode().strip()


def parse_time(s):
    h, m = map(int, s.split(":"))
    return dtime(h, m)

def obtain_timings(path):
    with open(path) as f:
        schedule = json.load(f)
        times = {k: parse_time(v) for k, v in schedule.items()}
        return times

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
                        to identify every medicine mentioned and extract exactly three fields for each:

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
                        3. timing — a JSON array of 24-hour time strings ("HH:MM") representing each 
                        dose time, calculated using the person's actual daily schedule provided below:
                                {obtain_timings("schedule.json")}
                        TIMING RULES:
                        - If the prescription gives a relative instruction like "30 min after lunch", 
                        "before dinner", "1 hour after breakfast", "at bedtime", etc., calculate the 
                        actual clock time by adding/subtracting the stated offset (in minutes) to/from 
                        the corresponding reference time above.
                        - "after <meal>" → reference time + offset (default offset if unspecified: 30 min)
                        - "before <meal>" → reference time - offset (default offset if unspecified: 30 min)
                        - "at <meal>" / "with <meal>" → reference time exactly (offset 0)
                        - "at bedtime" / "HS" → bed time exactly
                        - If the prescription only gives generic labels with no explicit meal/offset 
                        reference (e.g. "morning", "afternoon", "evening", "night"), map them to the 
                        nearest reference point as a default:
                        - morning → breakfast time
                        - afternoon → lunch time
                        - evening → dinner time - 3 hours (approx early evening), only if explicitly used
                        - night → dinner time
                        - HS → bed time
                        - If frequency is 1 but no specific time is mentioned, default to breakfast time.
                        - If frequency is 2 and no time given, default to [breakfast time, dinner time].
                        - If frequency is 3 and no time given, default to [breakfast time, lunch time, dinner time].
                        - If frequency is 4 and no time given, default to [breakfast time, lunch time, 
                            dinner time, bed time].
                        - All computed times must be output strictly as "HHMM" in 24-hour format, 
                        adjusted correctly across hour boundaries (e.g. if lunch is "1315" and offset 
                        is "30 min after", result is "1345"; if offset crosses into the next hour or 
                        day, roll over correctly).
                        - The number of entries in the timing array MUST always match the frequency value.
                        - If nothing can be inferred (no frequency, no reference times, no labels), 
                        output null.

                        SAME MEDICINE AT DIFFERENT TIMES:
                        If a medicine appears multiple times in the prescription with different timings 
                        or doses (e.g. "Metformin 500mg morning, Metformin 1000mg night"), create a 
                        SEPARATE object for each entry, with a "note" field describing the distinction 
                        (e.g. dose strength, condition). If there is no distinguishing note, still 
                        create separate objects — do not merge them.

                        STRICT OUTPUT RULES:
                        - Output ONLY a JSON array. No explanations, no preamble, no markdown, no extra text.
                        - One object per medicine entry, in the order they appear in the input.
                        - Use exactly these keys: "medicine", "frequency", "timing", and optionally "note".
                        - "timing" must always be a JSON array of "HH:MM" strings, never a plain string.
                        - If the OCR text contains no identifiable medicines, output: []
                        - Do not invent medicines that aren't in the text.
                        - Do not include dosage strength (mg/ml), doctor name, patient name, or duration 
                        (days/weeks) in the medicine field — only the three (or four) fields above.

                        OUTPUT FORMAT EXAMPLE (THIS IS JUST AN EXAMPLE):
                        [
                            {{"medicine": "Paracetamol", "frequency": 2, "timing": ["0800", "2100"]}},
                            {{"medicine": "Azithromycin", "frequency": 1, "timing": ["0800"]}}
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
        parsed_prescriptions = json.loads(_clean_json_text(raw_output))
    except json.JSONDecodeError as e:
        print(f"[warn] Could not parse model output as JSON: {e}")
        parsed_prescriptions = []

    with open("output.json", "w", encoding="utf-8") as file:
        json.dump(parsed_prescriptions, file, indent=4)

    print(f"Saved {len(parsed_prescriptions)} medicine entr{'y' if len(parsed_prescriptions)==1 else 'ies'} to output.json")

