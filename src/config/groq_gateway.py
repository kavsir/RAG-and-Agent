from langchain_groq import ChatGroq
import itertools
import time
from typing import Optional

# ========================
# API KEYS
# ========================
# Bạn cần điền ít nhất một key vào đây
GROQ_KEYS = [
    "#"
]

# ========================
# KEY ROTATION
# ========================
key_cycle = itertools.cycle(GROQ_KEYS) if GROQ_KEYS else None

def get_llm(model: str = "llama-3.1-8b-instant", temperature: float = 0):
    if not GROQ_KEYS:
        raise ValueError("Chưa cấu hình GROQ_KEYS trong groq_gateway.py")
    api_key = next(key_cycle)
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=temperature
    )

# ========================
# SAFE INVOKE
# ========================
def invoke_llm(prompt, retries=3, model: str = "llama-3.1-8b-instant", temperature: float = 0):
    for _ in range(retries):
        try:
            llm = get_llm(model=model, temperature=temperature)
            response = llm.invoke(prompt)
            return response.content
        except Exception as e:
            print("Groq error, switching key:", e)
            time.sleep(1)
    return "I'm temporarily unable to answer."