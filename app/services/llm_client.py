import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

if not TOGETHER_API_KEY:
    raise RuntimeError("❌ TOGETHER_API_KEY not found in environment!")

API_URL = "https://api.together.xyz/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {TOGETHER_API_KEY}",
    "Content-Type": "application/json"
}

MODEL_NAME = "meta-llama/Llama-3-8b-chat-hf"

async def query_together(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that answers only about Varun Gandhi."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 512,
        "top_p": 0.9
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(API_URL, headers=HEADERS, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("❌ Together API Error:", e)
            return "⚠️ Failed to contact LLM."
