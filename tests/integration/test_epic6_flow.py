import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_ssr_index_view():
    """US-20: Verificación de interfaz SSR con Tailwind CSS v4, dropzone y gestión de parámetros."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text

    # Verificar dropzone interactiva y contenedores clave
    assert "dropzone-area" in html
    assert "active-params-container" in html
    assert "file-input" in html
    assert "param-input" in html

    # Verificar presencia de chips predefinidos
    assert "Total" in html
    assert "Fecha" in html
    assert "NIT" in html


def test_ssr_resultados_view():
    """US-22: Vista de dictamen forense y hallazgos enriquecidos con métricas y desglose."""
    test_hash = "abc123mockhash456"
    response = client.get(f"/resultados/{test_hash}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text

    # Verificar tarjetas de métricas
    assert "Dictamen Documental" in html
    assert "Caché" in html
    assert "Páginas" in html
    assert "Tiempo Total" in html

    # Verificar tabla de hallazgos
    assert "Hallazgos Enriquecidos" in html
    assert "Parámetro" in html
    assert "Valor Extraído" in html
    assert "Método" in html
    assert "Score" in html

    # Verificar chat y telemetría
    assert "Pydective Chat" in html
    assert "Desglose por Página" in html


def test_sse_realtime_streaming_flow():
    """US-21: Transmisión reactiva de progreso en tiempo real mediante Server-Sent Events (/procesar/stream)."""
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    assert pdf_path.exists()

    with open(pdf_path, "rb") as f:
        files = {"file": ("digital_factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, facturacion"}
        response = client.post("/procesar/stream", files=files, data=data)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = []
    for line in response.text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)

    # Debe contener eventos de inicio, por cada página, y de finalización
    tipos = [e["tipo"] for e in events]
    assert "inicio" in tipos
    assert "pagina" in tipos
    assert "completado" in tipos

    # Verificar evento completado
    comp = [e for e in events if e["tipo"] == "completado"][0]
    assert comp["status"].lower() == "complete"
    assert len(comp["pdf_hash"]) == 64
    assert comp["paginas_totales"] == 1
    assert len(comp["hallazgos"]) >= 1


def test_chat_api_endpoint_flow():
    """US-23: Pydective Chat interactivo sobre documento procesado y 404 ante hash inexistente."""
    # 1. Error 404 para hash no existente o expirado
    unknown_hash = "0" * 64
    res_404 = client.post(
        f"/chat/{unknown_hash}",
        json={"pregunta": "¿Cuál es el valor?"},
    )
    assert res_404.status_code == 404
    assert res_404.json()["error"] == "DOCUMENT_NOT_FOUND_OR_EXPIRED"

    # 2. Procesar documento mediante SSE stream para registrarlo en caché
    pdf_path = FIXTURES_DIR / "digital_factura.pdf"
    with open(pdf_path, "rb") as f:
        files = {"file": ("digital_factura.pdf", f, "application/pdf")}
        data = {"parametros": "total, facturacion"}
        res_proc = client.post("/procesar/stream", files=files, data=data)

    # Extraer el hash generado
    pdf_hash = None
    for line in res_proc.text.split("\n"):
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev["tipo"] == "completado":
                pdf_hash = ev["pdf_hash"]
                break

    assert pdf_hash is not None

    # 3. Consulta de Chat con grounding y citas obligatorias [Página X]
    res_chat = client.post(
        f"/chat/{pdf_hash}",
        json={"pregunta": "¿Cuál es el total de la factura?"},
    )
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert "[Página 1]" in chat_data["citas"]
    assert len(chat_data["evidencias_relacionadas"]) >= 1
    assert "[Página 1]" in chat_data["respuesta"]

    # 4. Consulta sobre un parámetro inexistente (declinación sin alucinación)
    res_chat_absent = client.post(
        f"/chat/{pdf_hash}",
        json={"pregunta": "¿Cuál es la marca del vehículo de transporte?"},
    )
    assert res_chat_absent.status_code == 200
    chat_absent_data = res_chat_absent.json()
    assert chat_absent_data["citas"] == []
    assert "no figura registrado" in chat_absent_data["respuesta"]
