from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class BaseLLMProvider(ABC):
    """
    Contrato base unificado para proveedores de modelos LLM (Cloud y Local).
    Permite alternar transparentemente entre Gemini API y modelos locales (Ollama/llama.cpp/Kev).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre identificador del proveedor."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica disponibilidad y conectividad del proveedor."""
        pass

    @abstractmethod
    def generate_chat_response(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        image_bytes: Optional[bytes] = None,
        image_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Genera una respuesta en lenguaje natural para el asistente conversacional,
        con soporte opcional de inspección de imagen (multimodal o vía archivo).
        """
        pass

