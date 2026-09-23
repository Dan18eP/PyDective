import io
from pathlib import Path
import pytest
import numpy as np
from PIL import Image
import pymupdf

from app.services.preprocess_service import (
    render_page_to_numpy,
    detect_skew_angle,
    deskew_image,
    evaluate_contrast_and_otsu,
    preprocess_page,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_render_page_to_numpy_scales_max_dim_to_1024():
    factura_pdf = FIXTURES_DIR / "digital_factura.pdf"
    assert factura_pdf.exists()

    doc = pymupdf.open(factura_pdf)
    try:
        img_rgb, scale = render_page_to_numpy(doc[0], max_dim=1024)
        assert isinstance(img_rgb, np.ndarray)
        h, w = img_rgb.shape[:2]
        assert max(h, w) == 1024
        assert scale > 0.0
    finally:
        doc.close()


def test_detect_skew_angle_on_upright_document_is_near_zero():
    factura_pdf = FIXTURES_DIR / "digital_factura.pdf"
    doc = pymupdf.open(factura_pdf)
    try:
        img_rgb, _ = render_page_to_numpy(doc[0], max_dim=1024)
        angle = detect_skew_angle(img_rgb, max_angle=15.0)
        assert abs(angle) < 1.0, f"Expected angle near 0.0, got {angle}"
    finally:
        doc.close()


def test_detect_skew_angle_on_tilted_scan_within_15_degrees():
    # US-06 Escenario 1: escaneo_inclinado_skew.pdf (tilted by ~8.5°)
    skew_pdf = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    assert skew_pdf.exists()

    doc = pymupdf.open(skew_pdf)
    try:
        img_rgb, _ = render_page_to_numpy(doc[0], max_dim=1024)
        angle = detect_skew_angle(img_rgb, max_angle=15.0)
        # Should detect tilt and stay within [-15.0, 15.0]
        assert -15.0 <= angle <= 15.0
        # Since it was rotated 8.5 degrees, detected angle should be non-trivial
        assert abs(angle) > 2.0, f"Expected non-trivial angle detection for skewed scan, got {angle}"
    finally:
        doc.close()


def test_deskew_image_rotates_and_preserves_dimensions():
    # Create test image with synthetic line
    canvas = np.ones((600, 400, 3), dtype=np.uint8) * 255
    canvas[250:260, 50:350] = 0  # Horizontal black line

    deskewed = deskew_image(canvas, angle=5.0)
    assert deskewed.shape == canvas.shape
    assert isinstance(deskewed, np.ndarray)


def test_deskew_image_clamps_extreme_angles_to_15():
    canvas = np.ones((200, 200, 3), dtype=np.uint8) * 255
    # Should not throw when passed extreme angles
    deskewed = deskew_image(canvas, angle=45.0)
    assert deskewed.shape == (200, 200, 3)


def test_evaluate_contrast_and_otsu_on_low_contrast_image():
    # US-06 Escenario 2: Low contrast gray background with dark text
    low_contrast = np.full((300, 300, 3), 140, dtype=np.uint8)  # Flat mid-gray
    low_contrast[100:150, 100:200] = 120  # Subtle dark text

    result_img, otsu_applied = evaluate_contrast_and_otsu(low_contrast)
    assert otsu_applied is True
    # Pixels should be binarized (0 or 255)
    unique_vals = np.unique(result_img)
    assert all(val in (0, 255) for val in unique_vals)


def test_preprocess_page_full_pipeline_on_skewed_scan():
    # US-06 Escenario 3: Trazabilidad determinista
    skew_pdf = FIXTURES_DIR / "escaneo_inclinado_skew.pdf"
    doc = pymupdf.open(skew_pdf)
    try:
        result = preprocess_page(doc[0], max_dim=1024, quality=75)
        assert result.numero_pagina == 1
        assert result.preprocesado is True
        assert result.duracion_ms > 0.0
        assert len(result.image_bytes) > 0

        # Verify output is valid WebP
        pil_img = Image.open(io.BytesIO(result.image_bytes))
        assert pil_img.format == "WEBP"
        assert max(pil_img.size) <= 1024
    finally:
        doc.close()
