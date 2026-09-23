class PydectiveError(Exception):
    """Base error for all PyDective domain exceptions."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentoInvalidoError(PydectiveError):
    def __init__(self, message: str = "El archivo provisto no es un PDF válido o está corrupto."):
        super().__init__(message, code="INVALID_PDF")


class ExcesoPaginasError(PydectiveError):
    def __init__(self, max_pages: int, total_pages: int):
        super().__init__(
            f"El documento excede el límite máximo permitido de {max_pages} páginas (recibidas: {total_pages}).",
            code="PAGE_LIMIT_EXCEEDED"
        )
        self.max_pages = max_pages
        self.total_pages = total_pages


class ParametrosVaciosError(PydectiveError):
    def __init__(self, message: str = "Debe proporcionar al menos un parámetro de búsqueda no vacío."):
        super().__init__(message, code="EMPTY_SEARCH_PARAMETERS")


class DocumentoNoEncontradoOExpiradoError(PydectiveError):
    def __init__(self, pdf_hash: str):
        super().__init__(
            f"El documento con hash {pdf_hash} no se encuentra en memoria o su sesión ha expirado (TTL 24h).",
            code="DOCUMENT_NOT_FOUND_OR_EXPIRED"
        )
        self.pdf_hash = pdf_hash


class DeadlineExcedidoError(PydectiveError):
    def __init__(self, seconds: float):
        super().__init__(
            f"Se alcanzó el deadline global de procesamiento ({seconds}s).",
            code="GLOBAL_DEADLINE_EXCEEDED"
        )
        self.seconds = seconds


class KeysAgotadasError(PydectiveError):
    def __init__(self, message: str = "Todas las claves de API de Gemini se encuentran en cooldown o agotadas."):
        super().__init__(message, code="ALL_API_KEYS_EXHAUSTED")
