import json
import re
import hashlib
import unicodedata
from typing import List, Tuple, Union

from app.domain.errors import ParametrosVaciosError

# Diccionario base de sinónimos y variaciones léxicas comunes en español/inglés
# Nota: PyDective es agnóstico a documentos; si un parámetro no está en este mapa,
# su lista de búsqueda canónica contendrá simplemente el parámetro normalizado.
SYNONYMS_MAP = {
    "total": [
        "total",
        "valor total",
        "importe total",
        "monto total",
        "total a pagar",
        "gran total",
        "total factura",
    ],
    "subtotal": [
        "subtotal",
        "sub total",
        "base imponible",
        "base gravable",
        "valor bruto",
        "importe bruto",
    ],
    "iva": [
        "iva",
        "impuesto",
        "impuesto sobre las ventas",
        "valor iva",
        "tarifa iva",
        "tax",
    ],
    "fecha": [
        "fecha",
        "fecha de emision",
        "fecha de expedicion",
        "fecha factura",
        "fecha de creacion",
        "fecha documento",
    ],
    "fecha de vencimiento": [
        "fecha de vencimiento",
        "vencimiento",
        "fecha limite",
        "fecha plazo",
    ],
    "nit": [
        "nit",
        "numero de identificacion tributaria",
        "identificacion",
        "rut",
        "cuit",
        "rfc",
        "cif",
        "tax id",
    ],
    "factura": [
        "factura",
        "factura electronica",
        "factura de venta",
        "numero de factura",
        "invoice",
    ],
    "proveedor": [
        "proveedor",
        "emisor",
        "razon social",
        "vendedor",
        "nombre proveedor",
    ],
    "cliente": [
        "cliente",
        "adquirente",
        "comprador",
        "senor(es)",
        "destinatario",
    ],
}


def normalize_parameter(text: str) -> str:
    """
    Normaliza un término lingüístico aplicando la secuencia:
    1. Descomposición Unicode NFKD (despliega ligaduras como 'fi' -> 'fi' y diacríticos).
    2. Filtrado de marcas diacríticas / acentos ASCII.
    3. Casefold para insensibilidad total a mayúsculas/minúsculas.
    4. Colapso de espacios múltiples y limpieza de extremos.
    """
    if not text:
        return ""

    # Normalización NFKD: separa caracteres base de diacríticos y descompone ligaduras tipográficas
    nfkd_form = unicodedata.normalize("NFKD", text)

    # Elimina marcas diacríticas (acentos, tildes, diéresis)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    # Casefold para insensibilidad a mayúsculas
    lowered = only_ascii.casefold()

    # Eliminar signos de puntuación iniciales/finales indeseados manteniendo espacios internos
    cleaned = re.sub(r"[^\w\s-]", " ", lowered)

    # Colapsar espacios continuos
    collapsed = re.sub(r"\s+", " ", cleaned).strip()

    return collapsed


def canonicalize_parameters(raw_input: Union[str, List[str]]) -> Tuple[List[str], str]:
    """
    Procesa, limpia, deduplica y ordena alfabéticamente una lista de parámetros de búsqueda.

    Args:
        raw_input: Cadena JSON ('["total", "fecha"]'), cadena delimitada por comas ('total, fecha'),
                   o lista de cadenas.

    Returns:
        Tuple[List[str], str]: (lista_canonica_ordenada, query_hash_sha256)

    Raises:
        ParametrosVaciosError: Si no se provee ningún parámetro o todos quedan vacíos tras la normalización.
    """
    items: List[str] = []

    if isinstance(raw_input, str):
        raw_stripped = raw_input.strip()
        if not raw_stripped:
            raise ParametrosVaciosError()

        # Intentar parsear como JSON primero
        try:
            parsed = json.loads(raw_stripped)
            if isinstance(parsed, list):
                items = [str(x) for x in parsed]
            else:
                items = [str(parsed)]
        except (json.JSONDecodeError, TypeError):
            # Si no es JSON, separar por comas o saltos de línea
            items = [item.strip() for item in re.split(r"[,;\n]+", raw_stripped)]
    elif isinstance(raw_input, list):
        items = [str(x) for x in raw_input]
    else:
        raise ParametrosVaciosError("El formato de parámetros provisto no es compatible.")

    # Normalizar cada ítem y descartar cadenas vacías
    normalized_set = set()
    for item in items:
        norm = normalize_parameter(item)
        if norm:
            normalized_set.add(norm)

    if not normalized_set:
        raise ParametrosVaciosError("Debe proporcionar al menos un parámetro de búsqueda válido tras la normalización.")

    # Ordenar alfabéticamente para conformar la tupla canónica L0
    canonical_list = sorted(normalized_set)

    # Generar hash determinista de la consulta L0 (SHA-256 truncado a 16 caracteres hex)
    query_signature = "|".join(canonical_list).encode("utf-8")
    query_hash = hashlib.sha256(query_signature).hexdigest()[:16]

    return canonical_list, query_hash


def expand_parameter_synonyms(param: str) -> List[str]:
    """
    Expande un parámetro canónico en sus variantes sinónimas para la búsqueda heurística / regex.
    Si el parámetro no cuenta con una lista predefinida, retorna una lista con el parámetro original.
    """
    norm = normalize_parameter(param)
    synonyms = SYNONYMS_MAP.get(norm, [norm])

    # Asegurarse de que el término exacto esté en la primera posición y sin duplicados
    result = [norm]
    for s in synonyms:
        s_norm = normalize_parameter(s)
        if s_norm and s_norm not in result:
            result.append(s_norm)

    return result
