import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("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")

if not key:
    print("❌ ERROR: GROQ_API_KEY not found in .env file!")
    print("   Make sure .env is in the same folder as this script.")
else:
    print(f"✅ Key loaded successfully: {key[:10]}...{key[-4:]}")
    if "gsk_" not in key:
        print("   ⚠️  WARNING: Groq keys usually start with 'gsk_'")