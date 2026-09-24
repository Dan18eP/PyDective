import logging
from typing import Optional

from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.local_provider import LocalLLMProvider
from app.settings import settings

logger = logging.getLogger("pydective.providers.factory")


def get_llm_provider(preference: Optional[str] = None) -> BaseLLMProvider:
    """
    Fábrica que resuelve el proveedor de LLM activo según configuración ('auto', 'local', 'gemini').
    
    Estrategia de selección:
    - 'gemini': Instancia GeminiProvider.
    - 'local': Instancia LocalLLMProvider.
    - 'auto': Evalúa disponibilidad: si el endpoint local responde en <1s (Ollama/llama.cpp/Kev),
              prioriza el procesamiento local en CPU Ryzen 5500. De lo contrario, utiliza Gemini Cloud.
    """
    pref = (preference or settings.LLM_PROVIDER or "auto").lower()

    if pref == "gemini":
        return GeminiProvider()

    if pref == "local":
        return LocalLLMProvider()

    # Modo 'auto': Comprobación dinámica de conectividad local
    local_p = LocalLLMProvider()
    if local_p.is_available():
        logger.info(f"Modo auto: Proveedor local activo en {local_p.base_url} ({local_p.model_name})")
        return local_p

    # Fallback a Gemini Cloud si hay llaves disponibles
    gemini_p = GeminiProvider()
    if gemini_p.is_available():
        logger.info("Modo auto: Proveedor Gemini Cloud activo")
        return gemini_p

    # Retornar LocalLLMProvider por defecto para permitir diagnóstico de conexión
    return local_p
