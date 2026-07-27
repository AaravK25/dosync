import openai 
import base64

image_path= r"C:\Users\aarav\Downloads\Mobile Devices\PXL_20260727_155215076.MP.jpg"

def encode_image(image_path):
    with open(image_path,"rb") as image_file:
        return base64.b64encode(image_file.read()).decode().strip()


image_b64 = encode_image(image_path)

paddle = openai.OpenAI(
    base_url="http://127.0.0.1:8080",
    api_key="sk_no_api_key_required"
)

qwen = openai.OpenAI(
    base_url="http://127.0.0.1:8081",
    api_key="sk_no_api_key_required"
)


ocr = paddle.responses.create(
    model="Paddle-VL-0.9b",
    input= [
        {
            "role":"user",
            "content":[
                {
                    "type": "input_image",
                    "image_url": image_b64
                }
            ]
        }
    ]
)


text = ocr.output_text

response = qwen.responses.create(
    model="Qwen3.5-2b-UD-Q4_K_XL",
    input= [
        {
            "role":"user",
            "content":[
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
                    3. timing — when it should be taken, using ONLY these fixed labels (choose all 
                    that apply, comma-separated, in this order): "morning", "afternoon", "evening", 
                    "night". Map common abbreviations:
                    - HS → night
                    - AC (before food) / PC (after food) → keep timing labels only; ignore 
                      food-relation words, they are not part of this system.
                    If frequency is 1 but no specific time is mentioned, default to "morning".
                    If frequency is 2 and no time given, default to "morning, night".
                    If frequency is 3, default to "morning, afternoon, night".
                    If nothing can be inferred, output null.

                    STRICT OUTPUT RULES:
                    - Output ONLY a JSON array. No explanations, no preamble, no markdown, no extra text.
                    - One object per medicine, in the order they appear in the input.
                    - Use exactly these keys: "medicine", "frequency", "timing".
                    - If the OCR text contains no identifiable medicines, output: []
                    - Do not invent medicines that aren't in the text.
                    - Do not include dosage strength (mg/ml), doctor name, patient name, or duration 
                    (days/weeks) — only the three fields above.

                    OUTPUT FORMAT EXAMPLE:
                    [
                        {{"medicine": "Paracetamol", "frequency": 2, "timing": "morning, night"}},
                        {{"medicine": "Azithromycin", "frequency": 1, "timing": "morning"}}
                    ]

                    Now process the following OCR text and return only the JSON array:

                    {text}"""
                }
            ]
        }
    ]
)


json_array=response.output_text

print(json_array)