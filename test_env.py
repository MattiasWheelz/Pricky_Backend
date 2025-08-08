import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("HUGGINGFACE_API_KEY")
print("✅ LOADED:", key if key else "❌ NOT FOUND")
