import logging
from typing import Optional, List

from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.cli_provider import AgyCLIProvider, OpenCodeCLIProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.local_provider import LocalLLMProvider
from app.settings import settings

logger = logging.getLogger("pydective.providers.factory")


class LLMChainProvider(BaseLLMProvider):
    """
    Proveedor en cadena (Chain of Responsibility) con orden prioritario:
    1. agy (terminal CLI)
    2. opencode (terminal CLI)
    3. gemini (Google GenAI API)
    Fallback opcional a local_llm si ninguno de los anteriores está disponible.
    """

    def __init__(self, providers: Optional[List[BaseLLMProvider]] = None):
        self.last_used_provider: Optional[str] = None
        if providers:
            self._providers = providers
        else:
            self._providers = [
                AgyCLIProvider(),
                OpenCodeCLIProvider(),
                GeminiProvider(),
            ]

    @property
    def name(self) -> str:
        active_names = [p.name for p in self._providers if p.is_available()]
        return f"chain[{' -> '.join(active_names) or 'none'}]"

    def is_available(self) -> bool:
        return any(p.is_available() for p in self._providers)

    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
    ) -> Optional[str]:
        for provider in self._providers:
            if not provider.is_available():
                logger.debug(f"Proveedor {provider.name} no está disponible; probando siguiente en la cadena.")
                continue

            logger.info(f"Intentando generar respuesta con proveedor: {provider.name}")
            try:
                resp = provider.generate_chat_response(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    image_bytes=image_bytes,
                    image_path=image_path,
                )
                if resp and resp.strip():
                    self.last_used_provider = provider.name
                    logger.info(f"Respuesta generada exitosamente con proveedor: {provider.name}")
                    return resp.strip()
            except Exception as exc:
                logger.warning(f"Fallo en proveedor {provider.name}: {exc}. Continuando con fallback...")

        logger.error("Todos los proveedores en la cadena fallaron al generar respuesta.")
        return None


def get_llm_provider(preference: Optional[str] = None) -> BaseLLMProvider:
    """
    Fábrica que resuelve el proveedor de LLM activo según configuración:
    - 'chain': Orden prioritario: AGY CLI -> OpenCode CLI -> Gemini Cloud.
    - 'agy': Directo a AGY CLI.
    - 'opencode': Directo a OpenCode CLI.
    - 'gemini': Instancia GeminiProvider.
    - 'local': Instancia LocalLLMProvider.
    - 'auto': Cadena agy -> opencode -> gemini -> local.
    """
    pref = (preference or settings.LLM_PROVIDER or "chain").lower()

    if pref == "agy":
        return AgyCLIProvider()

    if pref == "opencode":
        return OpenCodeCLIProvider()

    if pref == "gemini":
        return GeminiProvider()

    if pref == "local":
        return LocalLLMProvider()

    if pref == "auto":
        # Modo 'auto' clásico: Comprobación dinámica de conectividad local
        local_p = LocalLLMProvider()
        if local_p.is_available():
            logger.info(f"Modo auto: Proveedor local activo en {local_p.base_url} ({local_p.model_name})")
            return local_p

        gemini_p = GeminiProvider()
        if gemini_p.is_available():
            logger.info("Modo auto: Proveedor Gemini Cloud activo")
            return gemini_p

        return local_p

    # Modo 'chain' por defecto: agy -> opencode -> gemini -> local
    chain = [
        AgyCLIProvider(),
        OpenCodeCLIProvider(),
        GeminiProvider(),
        LocalLLMProvider(),
    ]
    return LLMChainProvider(chain)

