import logging
import os
from typing import Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from app.services.providers.base_provider import BaseLLMProvider
from app.settings import settings

logger = logging.getLogger("pydective.providers.gemini")


class GeminiProvider(BaseLLMProvider):
    """
    Proveedor para Google Gemini Cloud API (ej. gemini-2.5-flash-lite).
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.GEMINI_MODEL

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
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
    ) -> Optional[str]:
        if not self.is_available():
            return None

        active_key = settings.api_keys_list[0]
        try:
            client = genai.Client(api_key=active_key)
            config = None
            if system_instruction and types is not None:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                )

            contents = [prompt]

            # Inyectar imagen si está disponible para razonamiento multimodal directo
            if types is not None:
                if image_bytes:
                    contents.append(
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                    )
                elif image_path and os.path.exists(image_path):
                    with open(image_path, "rb") as f:
                        contents.append(
                            types.Part.from_bytes(data=f.read(), mime_type="image/png")
                        )

            kwargs = {"model": self.model_name, "contents": contents}
            if config:
                kwargs["config"] = config

            response = client.models.generate_content(**kwargs)
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as exc:
            logger.warning(f"Error generando respuesta con GeminiProvider: {exc}")
            return None

