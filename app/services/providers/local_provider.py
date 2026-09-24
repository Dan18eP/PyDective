import logging
from typing import Optional, List, Dict, Any
import httpx

from app.services.providers.base_provider import BaseLLMProvider
from app.settings import settings

logger = logging.getLogger("pydective.providers.local")


class LocalLLMProvider(BaseLLMProvider):
    """
    Proveedor para LLMs locales vía API estándar compatible con OpenAI
    (Ollama, llama.cpp server, vLLM, Kev) ejecutándose localmente en CPU (AMD Ryzen 5 5500 con AVX2).
    Modelos recomendados:
    - qwen2.5:3b (Equilibrio óptimo en español y razonamiento legal, 35-45 t/s en Ryzen 5500)
    - llama3.2:3b
    - kev (Modelfile / checkpoint local)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.LOCAL_LLM_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.LOCAL_LLM_MODEL
        self.timeout = timeout or settings.LOCAL_LLM_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return f"local:{self.model_name}"

    def is_available(self) -> bool:
        """
        Verificación rápida no bloqueante (<1.0s) de conectividad hacia el endpoint local.
        """
        try:
            # Inspeccionar endpoint de modelos (/models)
            models_url = f"{self.base_url}/models"
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(models_url)
                return resp.status_code == 200
        except Exception:
            return False

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Optional[str]:
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024,
            "stream": False,
        }

        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        message = choices[0].get("message", {})
                        content = message.get("content", "").strip()
                        return content
                else:
                    logger.warning(
                        f"LocalLLMProvider returned status {resp.status_code}: {resp.text[:200]}"
                    )
                    return None
        except Exception as exc:
            logger.warning(f"Error conectando con LocalLLMProvider en {url}: {exc}")
            return None
