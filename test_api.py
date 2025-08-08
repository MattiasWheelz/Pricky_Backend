import httpx
import os
from dotenv import load_dotenv

load_dotenv()

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

API_URL = "https://api-inference.huggingface.co/models/google/flan-t5-small"
HEADERS = {
    "Authorization": f"Bearer {HUGGINGFACE_API_KEY}"
}

prompt = "What is the capital of India?"

payload = {
    "inputs": prompt,
    "parameters": {
        "max_new_tokens": 50
    }
}

try:
    response = httpx.post(API_URL, headers=HEADERS, json=payload, timeout=60.0)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:", response.json())
except Exception as e:
    print("❌ ERROR:", str(e))
