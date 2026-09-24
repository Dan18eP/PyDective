from pathlib import Path
import pymupdf
import pytest

from app.domain.models import MetadatoImagen
from app.services.image_service import (
    inventory_physical_images,
    classify_image_semantics,
    catalog_page_images,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_us13_physical_inventory_filters_decorative_and_keeps_relevant():
    # US-13 Escenario 1: Inventario físico local en Cero-IA (PyMuPDF)
    pdf_path = FIXTURES_DIR / "mixto_sello_firma.pdf"
    assert pdf_path.exists()
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    items = inventory_physical_images(page, min_dim_pt=80.0, min_area_ratio=0.005)
    # The fixture contains an official seal image and vector signature drawings
    assert len(items) >= 1

    for img in items:
        assert img.pagina == 1
        assert len(img.bbox) == 4
        # bbox has positive area
        assert img.bbox[2] > img.bbox[0]
        assert img.bbox[3] > img.bbox[1]
        assert img.area_ratio > 0.0

    doc.close()


def test_us13_semantic_classification_types():
    # US-13 Escenario 2: Clasificación semántica selectiva
    # 1. Firma manuscrita
    sig_meta = MetadatoImagen(
        id_imagen="sig_01",
        pagina=1,
        tipo_fisico="vector",
        bbox=[100.0, 500.0, 300.0, 580.0],
        area_ratio=0.05,
    )
    sig_label = classify_image_semantics(sig_meta, page_text="Firma del arrendador y representante legal")
    assert sig_label == "firma_manuscrita"

    # 2. Sello oficial
    seal_meta = MetadatoImagen(
        id_imagen="seal_01",
        pagina=1,
        tipo_fisico="raster",
        bbox=[350.0, 500.0, 480.0, 620.0],
        area_ratio=0.08,
    )
    seal_label = classify_image_semantics(seal_meta, page_text="Notaría Décima del Círculo de Bogotá")
    assert seal_label == "sello_oficial"

    # 3. Logotipo en cabecera
    logo_meta = MetadatoImagen(
        id_imagen="logo_01",
        pagina=1,
        tipo_fisico="raster",
        bbox=[50.0, 30.0, 150.0, 90.0],
        area_ratio=0.02,
    )
    logo_label = classify_image_semantics(logo_meta, page_text="EMPRESA S.A.S.")
    assert logo_label == "logotipo"


def test_us13_catalog_page_images_with_classification():
    pdf_path = FIXTURES_DIR / "mixto_sello_firma.pdf"
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    cataloged = catalog_page_images(page, catalogar_imagenes=True)
    assert len(cataloged) >= 1
    # Check that at least one item received a semantic classification
    labels = [img.clasificacion_semantica for img in cataloged]
    assert any(label in ("firma_manuscrita", "sello_oficial", "logotipo", "diagrama") for label in labels)

    doc.close()


def test_qr_code_opencv_detection_and_decoding():
    from app.services.image_service import detect_qr_with_opencv

    pdf_path = FIXTURES_DIR / "qr_sample.pdf"
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    images = inventory_physical_images(page)
    assert len(images) >= 1

    qr_img = images[0]
    is_qr, decoded = detect_qr_with_opencv(page, qr_img.bbox)
    assert is_qr is True
    assert decoded == "https://www.qrcode-monkey.com"

    doc.close()


def test_catalog_page_images_classifies_and_decodes_qr():
    pdf_path = FIXTURES_DIR / "qr_sample.pdf"
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]

    cataloged = catalog_page_images(page, catalogar_imagenes=True)
    assert len(cataloged) >= 1

    qr_item = next((img for img in cataloged if img.clasificacion_semantica == "codigo_qr"), None)
    assert qr_item is not None
    assert qr_item.clasificacion_semantica == "codigo_qr"
    assert qr_item.contenido_decodificado == "https://www.qrcode-monkey.com"

    doc.close()


def test_detect_morphological_visual_elements_on_scan_and_image():
    from app.services.image_service import detect_morphological_visual_elements
    from app.services.ingestion_service import validate_and_read_pdf

    fixtures_100_dir = Path(__file__).resolve().parent.parent / "fixtures_100"
    scan_path = fixtures_100_dir / "doc_051_escaneo.pdf"
    if scan_path.exists():
        doc = pymupdf.open(str(scan_path))
        page = doc[0]
        elements = detect_morphological_visual_elements(page)
        assert any(e.clasificacion_semantica == "sello_oficial" for e in elements)
        doc.close()

    img_path = fixtures_100_dir / "doc_061_img.png"
    if img_path.exists():
        data = img_path.read_bytes()
        _, doc, _ = validate_and_read_pdf(data, filename="doc_061_img.png")
        page = doc[0]
        elements = detect_morphological_visual_elements(page)
        assert any(e.clasificacion_semantica == "firma_manuscrita" for e in elements)
        doc.close()

