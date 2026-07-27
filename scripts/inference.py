import openai 
import base64
import requests

image_path= r"C:\Users\aarav\Downloads\images.png"

def encode_image(image_path):
    with open(image_path,"rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

paddle = openai.OpenAI(
    base_url="http://127.0.0.1:8080",
    api_key="sk_no_api_key_required"
)

qwen = openai.OpenAI(
    base_url="http://127.0.0.1:8081",
    api_key="sk_no_api_key_required"
)

ocr = paddle.chat.completions.create(
    model="Paddle-VL-0.9b",
    messages=[
        {"role":"system", "content": """You are an expert Optical Character Recognition (OCR) assistant specialized in converting visual document text into clean, structured Markdown.

        Your primary instructions:
        1. Extract ALL visible text accurately, preserving original capitalization, spelling, and punctuation.
        2. Structure the output using proper Markdown syntax (# for headings, - or 1. for lists, **bold**, *italics*).
        3. Format tables using standard Markdown table syntax (| Header | Header |).
        4. Do NOT hallucinate, guess, or invent missing text. If a word or phrase is completely illegible, replace it with [unclear].
        5. Do NOT output conversational filler, introductions, or explanations (e.g., "Here is the text from the image:"). Output ONLY the extracted content.
        """},
        {"role":"user", "content": [
            {"type": "text", "text":"Extract all contents."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(image_path)}"}}
        ]}
    ]
)

try:
    print(ocr.choices[0].messages)
except Exception as ex:
    print("Exception:", ex)