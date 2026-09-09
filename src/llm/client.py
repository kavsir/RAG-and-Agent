import json
import logging
import time
from typing import Optional, List, Dict, Generator
import httpx
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Fake/Mock response hook for offline testing
_MOCK_LLM_HANDLER = None

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
WRITE_TIMEOUT = 5.0
TOTAL_TIMEOUT = 25.0


def set_mock_llm_handler(handler):
    """Thiết lập mock handler cho kiểm thử offline."""
    global _MOCK_LLM_HANDLER
    _MOCK_LLM_HANDLER = handler


def is_live_llm_ready() -> bool:
    """Kiểm tra xem LLM API Key đã được cấu hình hợp lệ hay chưa."""
    key = settings.LLM_API_KEY
    return bool(key and key.strip() not in ("", "#", "your_api_key_here", "your_groq_api_key_here", "gsk_your_api_key_here"))


class LLMClient:
    """Gateway kết nối LLM trung lập, hỗ trợ OpenAI-compatible API và Groq với interactive latency budget."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.default_model = model or settings.LLM_MODEL
        self.timeout = timeout or TOTAL_TIMEOUT

    def _get_timeout_config(self) -> httpx.Timeout:
        """Interactive timeout budget: connect=5s, read=15s, total <= 30s."""
        return httpx.Timeout(
            self.timeout,
            connect=CONNECT_TIMEOUT,
            read=READ_TIMEOUT,
            write=WRITE_TIMEOUT,
            pool=5.0,
        )

    def invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 1,
    ) -> str:
        """Gửi prompt đến LLM và nhận câu trả lời dưới dạng text (interactive latency budget)."""
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
        attempt = 0
        while attempt <= max_retries:
            try:
                start_time = time.time()
                with httpx.Client(timeout=self._get_timeout_config()) as client:
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
                elif 400 <= resp.status_code < 500:
                    # 4xx client errors (400, 401, 403, 404, 429): ZERO RETRIES (Fail Fast)
                    logger.warning(
                        f"LLM API client error {resp.status_code}: {resp.text[:200]} - Không thử lại."
                    )
                    return f"Lỗi yêu cầu AI ({resp.status_code}): Vui lòng kiểm tra lại cấu hình tài khoản hoặc quyền truy cập."
                else:
                    # 5xx server errors: Cho phép thử lại tối đa max_retries
                    logger.warning(
                        f"LLM API server error {resp.status_code} (lần {attempt+1}/{max_retries+1}): {resp.text[:200]}"
                    )
                    last_err = f"API Error {resp.status_code}: {resp.text[:100]}"
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as net_err:
                logger.warning(f"LLM network/timeout error trên lần thử {attempt+1}: {net_err}")
                last_err = str(net_err)
            except Exception as e:
                logger.warning(f"Lỗi khi gọi LLM: {str(e)} (lần thử {attempt+1})")
                last_err = str(e)

            attempt += 1
            if attempt <= max_retries:
                time.sleep(0.5)

        logger.error(f"Gọi LLM thất bại hoàn toàn sau {attempt} lần: {last_err}")
        return "Xin lỗi, hiện tại tôi không thể kết nối đến máy chủ AI để xử lý câu trả lời. Vui lòng thử lại sau."

    def stream_invoke(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 1,
    ) -> Generator[str, None, None]:
        """Gọi LLM với provider streaming (stream=True), phát token trực tiếp đến người dùng."""
        global _MOCK_LLM_HANDLER
        if _MOCK_LLM_HANDLER is not None:
            full_text = _MOCK_LLM_HANDLER(prompt, system_prompt=system_prompt)
            import re
            words = re.findall(r"\S+\s*", full_text)
            for w in words:
                yield w
            return

        if not self.api_key or self.api_key.strip() in ("", "#", "your_api_key_here"):
            yield "Chưa cấu hình LLM_API_KEY trong file .env. Vui lòng cung cấp API key để tiếp tục."
            return

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
            "stream": True,
        }

        attempt = 0
        while attempt <= max_retries:
            try:
                with httpx.Client(timeout=self._get_timeout_config()) as client:
                    with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                        if resp.status_code == 200:
                            for line in resp.iter_lines():
                                line = line.strip()
                                if not line or line == "data: [DONE]":
                                    continue
                                if line.startswith("data: "):
                                    try:
                                        chunk_data = json.loads(line[6:])
                                        choices = chunk_data.get("choices", [])
                                        if choices:
                                            delta = choices[0].get("delta", {}).get("content", "")
                                            if delta:
                                                yield delta
                                    except Exception:
                                        continue
                            return
                        elif 400 <= resp.status_code < 500:
                            logger.warning(f"LLM stream client error {resp.status_code} - không thử lại.")
                            yield f"Lỗi yêu cầu AI ({resp.status_code})."
                            return
                        else:
                            logger.warning(f"LLM stream server error {resp.status_code} (lần {attempt+1})")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as net_err:
                logger.warning(f"LLM stream network error: {net_err}")
            except Exception as e:
                logger.warning(f"Lỗi LLM stream: {e}")

            attempt += 1
            if attempt <= max_retries:
                time.sleep(0.5)

        yield "Xin lỗi, hiện tại tôi không thể kết nối đến máy chủ AI để xử lý câu trả lời."


# Singleton client
_default_client = LLMClient()


def get_llm_client() -> LLMClient:
    return _default_client


def invoke_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    retries: int = 1,
) -> str:
    """Hàm gọi LLM nhanh dùng chung cho toàn bộ dự án (mặc định max 1 retry)."""
    return _default_client.invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=retries,
    )


def stream_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    retries: int = 1,
) -> Generator[str, None, None]:
    """Hàm gọi LLM streaming trực tiếp từ provider."""
    return _default_client.stream_invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_retries=retries,
    )

