"""
Legacy adapter for groq_gateway.
Chuyển tiếp toàn bộ cuộc gọi sang src.llm.client để đảm bảo tính trung lập về nhà cung cấp LLM.
"""
from src.llm.client import invoke_llm

__all__ = ["invoke_llm"]
