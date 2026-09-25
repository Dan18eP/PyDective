import json
import logging
from typing import Optional, List, Dict, Any, Generator
import httpx

from app.services.providers.base_provider import BaseLLMProvider
from app.services.hardware_adapter_service import (
    get_recommended_slm_model,
    get_optimal_thread_count,
)
from app.settings import settings

logger = logging.getLogger("pydective.providers.local")


class LocalLLMProvider(BaseLLMProvider):
    """
    Proveedor para LLMs locales vía API estándar compatible con OpenAI
    (Ollama, llama.cpp server, vLLM) ejecutándose en CPU (Intel o AMD).
    Se auto-calibra dinámicamente con hardware_adapter_service.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.LOCAL_LLM_BASE_URL).rstrip("/")
        # Si el modelo no está fijado en .env o settings, pedir recomendación al adaptador de hardware
        self.model_name = model_name or settings.LOCAL_LLM_MODEL or get_recommended_slm_model()
        self.timeout = timeout or settings.LOCAL_LLM_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return f"local:{self.model_name}"

    def is_available(self) -> bool:
        """
        Verificación rápida (<1.0s) de conectividad hacia el endpoint local
        y auto-selección del modelo ligero disponible en el equipo.
        """
        try:
            models_url = f"{self.base_url}/models"
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(models_url)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, dict):
                            model_list = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
                            if any(self.model_name in m for m in model_list):
                                return True
                            # Si el modelo preferido no está descargado, tomar el modelo de texto más rápido disponible
                            candidates = [m for m in model_list if not any(x in m for x in ("bge", "embed", "vision"))]
                            if candidates:
                                # Priorizar 1b o 0.5b si existen
                                light_candidates = [c for c in candidates if any(k in c for k in ("1b", "0.5b", "1.5b"))]
                                self.model_name = light_candidates[0] if light_candidates else candidates[0]
                                return True
                    except Exception:
                        pass
                    return True
            return False
        except Exception:
            return False

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Optional[str]:
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        threads = get_optimal_thread_count()

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 120,
            "stream": False,
            "options": {"num_thread": threads},
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

    def generate_chat_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Generator[str, None, None]:
        """
        Generador de streaming token por token para Server-Sent Events (Opción 3).
        El primer token aparece en < 350 ms en CPUs Intel o AMD.
        """
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        threads = get_optimal_thread_count()

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 120,
            "stream": True,
            "options": {"num_thread": threads},
        }

        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, json=payload) as response:
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        chunk_str = line[6:].strip()
                        if chunk_str == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(chunk_str)
                            choices = chunk_data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except Exception:
                            pass
        except Exception as exc:
            logger.warning(f"Error en streaming de LocalLLMProvider: {exc}")
