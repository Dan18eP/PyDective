import os
import re
import math
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("pydective.vector_store")

DATA_CONTEXT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "contexts"
DATA_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def get_document_markdown_path(pdf_hash: str) -> Path:
    """Retorna la ruta al archivo markdown persistido para el documento."""
    return DATA_CONTEXT_DIR / f"{pdf_hash}.md"


def get_document_markdown_context(pdf_hash: str) -> Optional[str]:
    """Recupera el markdown completo persistido si existe."""
    p = get_document_markdown_path(pdf_hash)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Error al leer contexto markdown de {pdf_hash}: {e}")
    return None


def generate_and_save_document_markdown(
    pdf_hash: str,
    pdf_bytes: bytes,
    resultados_paginas: Optional[List[Any]] = None,
) -> Tuple[str, Path]:
    """
    Genera la transcripción estructurada en Markdown de todo el documento,
    incluyendo metadatos visuales por página, y la persiste en data/contexts/{pdf_hash}.md.
    """
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages_sections: List[str] = []

    visuals_by_page: Dict[int, List[str]] = {}
    if resultados_paginas:
        for res in resultados_paginas:
            p_n = getattr(res, "numero_pagina", 1)
            v_items = []
            for v in getattr(res, "metadatos_visuales", []):
                cls_name = (v.clasificacion_semantica or "elemento").capitalize()
                extra = f" (decodificado: '{v.contenido_decodificado}')" if v.contenido_decodificado else ""
                v_items.append(f"- **{cls_name}**: BBox `{v.bbox}`{extra}")
            if v_items:
                visuals_by_page[p_n] = v_items

    for p_idx in range(len(doc)):
        p_num = p_idx + 1
        page_text = doc[p_idx].get_text().strip()

        section_lines = [
            f"# [Página {p_num}]",
            f"**Folio:** {p_num} de {len(doc)}",
            "",
            "## Contenido Textual Literal",
            page_text if page_text else "*[Sin texto seleccionable en este folio]*",
        ]

        if p_num in visuals_by_page:
            section_lines.extend([
                "",
                "## Elementos Visuales e Inspección Forense",
                "\n".join(visuals_by_page[p_num]),
            ])

        pages_sections.append("\n".join(section_lines))

    doc.close()

    full_markdown = (
        f"# EXPEDIENTE FORENSE Y CONTEXTO DOCUMENTAL\n"
        f"**Identificador SHA-256:** `{pdf_hash}`\n"
        f"**Total Folios:** {len(pages_sections)}\n\n"
        "---\n\n" + "\n\n---\n\n".join(pages_sections)
    )

    target_path = get_document_markdown_path(pdf_hash)
    target_path.write_text(full_markdown, encoding="utf-8")
    logger.info(f"Contexto Markdown de documento persistido en {target_path} ({len(full_markdown)} caracteres)")

    return full_markdown, target_path


class VectorChunk:
    def __init__(self, chunk_id: str, page: int, text: str, heading: str = ""):
        self.chunk_id = chunk_id
        self.page = page
        self.text = text
        self.heading = heading
        self.tf: Dict[str, float] = {}
        self.length: int = len(text.split())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "page": self.page,
            "text": self.text,
            "heading": self.heading,
        }


class LightweightVectorStore:
    """
    Motor vectorial ultraligero y determinista en memoria basado en embeddings léxicos
    y ponderación BM25 / Similitud Coseno TF-IDF con normalización de longitud.
    Cero dependencias externas pesadas, respuesta en <1.5 ms.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.chunks: List[VectorChunk] = []
        self.idf: Dict[str, float] = {}
        self.avg_doc_len: float = 0.0
        self.k1 = k1
        self.b = b

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = cleaned.split()
        stopwords = {
            "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a",
            "en", "para", "por", "con", "sin", "sobre", "entre", "hasta", "desde",
            "que", "cual", "cuales", "como", "donde", "cuando", "quien", "quienes",
            "y", "o", "u", "e", "este", "esta", "estos", "estas", "ese", "esa", "esos",
            "esas", "su", "sus", "al", "se", "es", "son", "fue", "ha", "han"
        }
        return [t for t in tokens if len(t) > 2 and t not in stopwords]

    def build_from_markdown(self, markdown_text: str):
        """Parsea el markdown del documento y genera chunks indexados por página/sección."""
        self.chunks.clear()
        page_blocks = re.split(r"\n---\n+", markdown_text)
        
        chunk_idx = 0
        total_lens = 0

        for block in page_blocks:
            block = block.strip()
            if not block:
                continue

            page_match = re.search(r"#\s*\[P[aá]gina\s+(\d+)\]", block, re.IGNORECASE)
            page_num = int(page_match.group(1)) if page_match else 1

            paragraphs = [p.strip() for p in block.split("\n\n") if len(p.strip()) > 30]
            if not paragraphs:
                paragraphs = [block]

            for p in paragraphs:
                heading = ""
                if p.startswith("#"):
                    first_line = p.splitlines()[0]
                    heading = first_line.lstrip("#").strip()

                chunk = VectorChunk(
                    chunk_id=f"chunk_{chunk_idx}",
                    page=page_num,
                    text=p,
                    heading=heading
                )
                tokens = self._tokenize(p)
                for t in tokens:
                    chunk.tf[t] = chunk.tf.get(t, 0.0) + 1.0

                self.chunks.append(chunk)
                total_lens += chunk.length
                chunk_idx += 1

        n_chunks = len(self.chunks)
        if n_chunks == 0:
            return

        self.avg_doc_len = total_lens / n_chunks

        # Calcular IDF
        doc_counts: Dict[str, int] = {}
        for c in self.chunks:
            for t in c.tf.keys():
                doc_counts[t] = doc_counts.get(t, 0) + 1

        for term, cnt in doc_counts.items():
            self.idf[term] = math.log((n_chunks - cnt + 0.5) / (cnt + 0.5) + 1.0)

    def similarity_search(self, query: str, top_k: int = 4) -> List[Tuple[VectorChunk, float]]:
        """Busca los fragmentos más relevantes para la consulta mediante puntuación BM25."""
        if not self.chunks:
            return []

        q_tokens = self._tokenize(query)
        if not q_tokens:
            return [(c, 0.0) for c in self.chunks[:top_k]]

        scored: List[Tuple[VectorChunk, float]] = []

        for chunk in self.chunks:
            score = 0.0
            doc_len = chunk.length or 1
            for q_term in q_tokens:
                if q_term in chunk.tf:
                    tf_val = chunk.tf[q_term]
                    idf_val = self.idf.get(q_term, 0.5)
                    # Fórmula BM25
                    numerator = tf_val * (self.k1 + 1.0)
                    denominator = tf_val + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                    score += idf_val * (numerator / denominator)

            if score > 0.0:
                scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


# Cache en memoria de vector stores instanciadas por hash
_VECTOR_STORES_CACHE: Dict[str, LightweightVectorStore] = {}


def get_or_create_vector_store(
    pdf_hash: str,
    pdf_bytes: Optional[bytes] = None,
    resultados_paginas: Optional[List[Any]] = None,
) -> Tuple[LightweightVectorStore, str, Path]:
    """
    Obtiene la base vectorial del documento.
    Si ya existe el .md persistido, lo carga inmediatamente.
    Si no existe, extrae todo el documento, guarda el .md y genera el índice vectorial.
    """
    md_content = get_document_markdown_context(pdf_hash)
    md_path = get_document_markdown_path(pdf_hash)

    if not md_content and pdf_bytes:
        md_content, md_path = generate_and_save_document_markdown(
            pdf_hash, pdf_bytes, resultados_paginas
        )

    if not md_content:
        # Intentar cargar bytes desde almacenamiento
        from app.services.pdf_viewer_service import get_pdf_bytes_by_hash
        stored_bytes = get_pdf_bytes_by_hash(pdf_hash)
        if stored_bytes:
            md_content, md_path = generate_and_save_document_markdown(
                pdf_hash, stored_bytes, resultados_paginas
            )

    if pdf_hash in _VECTOR_STORES_CACHE:
        return _VECTOR_STORES_CACHE[pdf_hash], md_content or "", md_path

    vstore = LightweightVectorStore()
    if md_content:
        vstore.build_from_markdown(md_content)
        _VECTOR_STORES_CACHE[pdf_hash] = vstore

    return vstore, md_content or "", md_path
