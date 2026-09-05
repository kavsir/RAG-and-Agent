import logging
import time
from typing import Optional, List, Dict
import httpx
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Fake/Mock response hook for offline testing
_MOCK_LLM_HANDLER = None


def set_mock_llm_handler(handler):
    """Thiết lập mock handler cho kiểm thử offline."""
    global _MOCK_LLM_HANDLER
    _MOCK_LLM_HANDLER = handler


def is_live_llm_ready() -> bool:
    """Kiểm tra xem LLM API Key đã được cấu hình hợp lệ hay chưa."""
    key = settings.LLM_API_KEY
    return bool(key and key.strip() not in ("", "#", "your_api_key_here", "your_groq_api_key_here", "gsk_your_api_key_here"))


class LLMClient:
    """Gateway kết nối LLM trung lập, hỗ trợ OpenAI-compatible API và Groq."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.default_model = model or settings.LLM_MODEL
        self.timeout = timeout or settings.LLM_TIMEOUT

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> str:
        """Gửi prompt đến LLM và nhận câu trả lời dưới dạng text."""
        global _MOCK_LLM_HANDLER
        if _MOCK_LLM_HANDLER is not None:
            return _MOCK_LLM_HANDLER(prompt, system_prompt=system_prompt)

        # Kiểm tra API Key
        if not self.api_key or self.api_key.strip() in ("", "#", "your_api_key_here"):
            logger.warning("LLM_API_KEY chưa được cấu hình hợp lệ trong .env")
            return "Chưa cấu hình LLM_API_KEY trong file .env. Vui lòng cung cấp API key để tiếp tục."

        active_model = model or self.default_model
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": active_model,
            "messages": messages,
            "temperature": temperature,
        }

        last_err = None
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(endpoint, json=payload, headers=headers)

                duration = time.time() - start_time
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "").strip()
                        logger.debug(f"LLM invoke thành công model={active_model} ({duration:.2f}s)")
                        return content
                    return ""
                else:
                    logger.warning(
                        f"LLM API trả về mã lỗi {resp.status_code} (lần {attempt+1}/{max_retries+1}): {resp.text[:200]}"
                    )
                    last_err = f"API Error {resp.status_code}: {resp.text[:100]}"
            except httpx.TimeoutException:
                logger.warning(f"LLM request timed out ({self.timeout}s) trên lần thử {attempt+1}")
                last_err = "Request timed out"
            except Exception as e:
                logger.warning(f"Lỗi khi gọi LLM: {str(e)} (lần thử {attempt+1})")
                last_err = str(e)

            if attempt < max_retries:
                time.sleep(1.0)

        logger.error(f"Gọi LLM thất bại hoàn toàn sau {max_retries+1} lần: {last_err}")
        return "Xin lỗi, hiện tại tôi không thể kết nối đến máy chủ AI để xử lý câu trả lời."


# Singleton client
_default_client = LLMClient()


def get_llm_client() -> LLMClient:
    return _default_client


def invoke_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    retries: int = 2,
) -> str:
    """Hàm gọi LLM nhanh dùng chung cho toàn bộ dự án."""
    return _default_client.invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=retries,
    )
