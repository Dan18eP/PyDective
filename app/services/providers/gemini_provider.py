import logging
from typing import Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from app.services.providers.base_provider import BaseLLMProvider
from app.services.key_pool_service import key_pool
from app.settings import settings

logger = logging.getLogger("pydective.providers.gemini")


class GeminiProvider(BaseLLMProvider):
    """
    Proveedor para Google Gemini Cloud API (ej. gemini-3.1-flash-lite).
    Incorpora rotación/conmutación de API Keys (KeyPoolManager) y tolerancia a fallos.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.GEMINI_MODEL
        # Modelo de respaldo si 3.1 sufre picos temporales de saturación (503 High Demand)
        self.fallback_model = "gemini-3.5-flash-lite"

    @property
    def name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        return genai is not None and bool(settings.api_keys_list)

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Optional[str]:
        if not self.is_available():
            return None

        def _call_gemini(api_key: str) -> Optional[str]:
            client = genai.Client(api_key=api_key)
            config = None
            if system_instruction and types is not None:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                )

            contents = [prompt]
            # Intentar primero con el modelo configurado (gemini-3.1-flash-lite)
            models_to_try = [self.model_name]
            if self.fallback_model not in models_to_try:
                models_to_try.append(self.fallback_model)

            last_model_exc = None
            for current_model in models_to_try:
                try:
                    kwargs = {"model": current_model, "contents": contents}
                    if config:
                        kwargs["config"] = config
                    response = client.models.generate_content(**kwargs)
                    if response and response.text:
                        return response.text.strip()
                except Exception as exc:
                    err_str = str(exc).lower()
                    last_model_exc = exc
                    # Si el error es 503 (high demand) o 404 en el modelo, intentar con el siguiente modelo de respaldo
                    if "503" in err_str or "high demand" in err_str or "unavailable" in err_str or "not_found" in err_str:
                        logger.warning(f"Modelo {current_model} experimentó saturación temporal (503). Intentando fallback...")
                        continue
                    # Si es error de cuota o rate limit (429), elevarlo para que key_pool active el switching de API key
                    raise exc

            if last_model_exc:
                raise last_model_exc
            return None

        try:
            result, used_key = key_pool.execute_with_failover(
                page_number=0,
                fn=_call_gemini,
                max_attempts=len(settings.api_keys_list) * 2,
            )
            return result
        except Exception as exc:
            logger.warning(f"Error generando respuesta con GeminiProvider tras agotar failover: {exc}")
            return None
