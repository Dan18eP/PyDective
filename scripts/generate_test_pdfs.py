#!/usr/bin/env python3
"""
PyDective PDF Fixtures Generator.

Generates realistic and diverse synthetic PDF test fixtures matching the
architectural test scenarios described in ADR-001, ADR-002, ADR-003, and ADR-004:
1. digital_factura.pdf - Clean digital invoice with native vector text (Fast Lane: LOCAL).
2. digital_contrato.pdf - 4-page legal lease contract with dynamic entities (Fast Lane: LOCAL).
3. mixto_sello_firma.pdf - Digital text with visual stamp and signature graphics (NEEDS_AI / catalog).
4. escaneo_limpio.pdf - Pure raster scan (0 digital text words, Lane: NEEDS_AI).
5. escaneo_inclinado_skew.pdf - Raster scan rotated 9 degrees to test OpenCV Deskew.
6. ocr_corrupto.pdf - Degraded OCR text layer with replacement chars and no spaces (Score fallback: NEEDS_AI).
7. multipage_stress_20p.pdf - 20-page stress test document at the platform's limit (RV-006 boundary).

Usage:
    uv run python scripts/generate_test_pdfs.py [--output-dir tests/fixtures]
"""

import os
import io
import math
import random
import argparse
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter


def create_digital_factura(output_path: Path):
    """Generates a clean digital invoice with native text and table structure."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Header branding
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 40, 545, 95))
    shape.finish(color=(0.1, 0.2, 0.4), fill=(0.95, 0.97, 1.0))
    shape.commit()

    page.insert_text(fitz.Point(65, 70), "SERVICIOS TECNOLÓGICOS DEL NORTE S.A.S.", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))
    page.insert_text(fitz.Point(65, 85), "NIT: 900.543.210-8  •  IVA Régimen Común  •  Bogotá D.C., Colombia", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))

    # Invoice Details Block
    page.insert_text(fitz.Point(400, 65), "FACTURA ELECTRÓNICA", fontsize=11, fontname="helv", color=(0.1, 0.2, 0.4))
    page.insert_text(fitz.Point(400, 80), "N° FE-2026-0842", fontsize=12, fontname="helv", color=(0.8, 0.1, 0.1))

    # Customer & Metadata Section
    page.insert_text(fitz.Point(50, 130), "FECHA DE EMISIÓN:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(170, 130), "2026-04-15", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(50, 150), "FECHA DE VENCIMIENTO:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(190, 150), "2026-05-15", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(50, 170), "ADQUIRIENTE:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(170, 170), "LOGÍSTICA Y TRANSPORTES ANDINOS S.A.", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(50, 190), "NIT / CÉDULA:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(170, 190), "830.123.987-1", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(50, 210), "CIUDAD:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(170, 210), "Medellín, Antioquia", fontsize=10, fontname="helv")

    # Table Header
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(50, 240, 545, 265))
    shape.finish(color=(0.1, 0.2, 0.4), fill=(0.15, 0.25, 0.45))
    shape.commit()

    page.insert_text(fitz.Point(60, 256), "Ítem / Descripción", fontsize=9, fontname="helv", color=(1, 1, 1))
    page.insert_text(fitz.Point(320, 256), "Cant.", fontsize=9, fontname="helv", color=(1, 1, 1))
    page.insert_text(fitz.Point(370, 256), "Vlr. Unitario", fontsize=9, fontname="helv", color=(1, 1, 1))
    page.insert_text(fitz.Point(460, 256), "Subtotal (COP)", fontsize=9, fontname="helv", color=(1, 1, 1))

    # Items
    items = [
        ("Suscripción Enterprise Servidor Cloud Dedicado (Abril)", "1", "$ 3.200.000", "$ 3.200.000"),
        ("Soporte Técnico Especializado Nivel 3 (40 horas)", "40", "$ 75.000", "$ 3.000.000"),
        ("Licenciamiento de Seguridad Endpoint Avanzado", "25", "$ 48.000", "$ 1.200.000"),
        ("Copia de Seguridad Inmutable Georedundante (2TB)", "1", "$ 650.000", "$ 650.000"),
    ]

    y = 285
    for desc, cant, vlr, sub in items:
        page.insert_text(fitz.Point(60, y), desc, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(325, y), cant, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(375, y), vlr, fontsize=9, fontname="helv")
        page.insert_text(fitz.Point(465, y), sub, fontsize=9, fontname="helv")
        y += 24

    # Table lines
    shape = page.new_shape()
    shape.draw_line(fitz.Point(50, y + 10), fitz.Point(545, y + 10))
    shape.finish(color=(0.7, 0.7, 0.7), width=0.8)
    shape.commit()

    # Totals block (Spatial neighborhood for key-value tests)
    y_tot = y + 35
    page.insert_text(fitz.Point(350, y_tot), "SUBTOTAL:", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(460, y_tot), "$ 8.050.000 COP", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(350, y_tot + 20), "IVA (19%):", fontsize=10, fontname="helv")
    page.insert_text(fitz.Point(460, y_tot + 20), "$ 1.529.500 COP", fontsize=10, fontname="helv")

    page.insert_text(fitz.Point(350, y_tot + 45), "TOTAL A PAGAR:", fontsize=12, fontname="helv")
    page.insert_text(fitz.Point(455, y_tot + 45), "$ 9.579.500 COP", fontsize=12, fontname="helv")

    # Payment details & footer
    page.insert_text(fitz.Point(50, 720), "FORMA DE PAGO: Transferencia Bancaria Electrónica (30 días)", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(50, 735), "BANCO: Bancolombia - Cuenta Corriente N° 102-938475-11", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(50, 750), "CUFE: 7a8f9c0e1d2b3a4f5e6d7c8b9a0f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8", fontsize=7.5, fontname="courier", color=(0.4, 0.4, 0.4))

    doc.save(output_path)
    doc.close()


def create_digital_contrato(output_path: Path):
    """Generates a 4-page legal lease contract with dynamic arbitrary entities."""
    doc = fitz.open()

    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(fitz.Point(120, 80), "CONTRATO DE ARRENDAMIENTO DE LOCAL COMERCIAL", fontsize=13, fontname="helv")
    p1.insert_text(fitz.Point(230, 100), "N° AR-2026-991", fontsize=11, fontname="helv", color=(0.3, 0.3, 0.3))

    p1.insert_textbox(
        fitz.Rect(50, 130, 545, 800),
        "Entre los suscritos a saber, de una parte ROBERTO ANTONIO JARAMILLO OSPINA, mayor de edad, "
        "domiciliado en la ciudad de Bogotá D.C., identificado con Cédula de Ciudadanía N° 79.432.890, "
        "quien en adelante se denominará EL ARRENDADOR; y de la otra parte, COMERCIALIZADORA ALIANZA "
        "GLOBAL S.A.S., sociedad comercial legalmente constituida según matrícula mercantil N° 02938491, "
        "con NIT: 901.884.231-3, representada legalmente por VALERIA MONTOYA DUQUE, identificada con Cédula "
        "de Ciudadanía N° 52.981.442, quien en adelante se denominará LA ARRENDATARIA, hemos acordado celebrar "
        "el presente contrato de arrendamiento que se regirá por el Código de Comercio de Colombia y las "
        "siguientes cláusulas especiales:\n\n"
        "CLÁUSULA PRIMERA. — OBJETO DEL CONTRATO: EL ARRENDADOR entrega a título de arrendamiento a "
        "LA ARRENDATARIA, y esta declara recibir a entera satisfacción, el inmueble ubicado en la "
        "Calle 93B N° 13-45 Local 102 del Edificio Centro Empresarial Chicó, en la ciudad de Bogotá D.C., "
        "con una superficie total construida de 184 metros cuadrados, destinado exclusivamente para el "
        "funcionamiento de oficinas de consultoría tecnológica y servicios de soporte digital.\n\n"
        "CLÁUSULA SEGUNDA. — VIGENCIA DEL CONTRATO: El término de duración del presente contrato será de "
        "TREINTA Y SEIS (36) MESES, contados formalmente a partir del día 01 de junio de 2026 hasta el "
        "31 de mayo de 2029, fecha en la cual terminará sin necesidad de desahucio judicial, salvo que las "
        "partes acuerden prórroga por escrito con mínimo tres (3) meses de antelación.",
        fontsize=10.5, fontname="helv", align=fitz.TEXT_ALIGN_JUSTIFY
    )

    # Page 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(fitz.Point(50, 60), "Contrato de Arrendamiento N° AR-2026-991 — Página 2 de 4", fontsize=8.5, fontname="helv", color=(0.5, 0.5, 0.5))

    p2.insert_textbox(
        fitz.Rect(50, 90, 545, 800),
        "CLÁUSULA TERCERA. — CANON MENSUAL DE ARRENDAMIENTO: LA ARRENDATARIA se obliga a pagar a "
        "EL ARRENDADOR por concepto de canon mensual de arrendamiento la suma de DOCE MILLONES QUINIENTOS "
        "MIL PESOS M/CTE ($ 12.500.000 COP), pagaderos por mes anticipado dentro de los primeros cinco (5) "
        "días calendario de cada periodo mensual, mediante transferencia a la cuenta bancaria designada.\n\n"
        "PARÁGRAFO PRIMERO: Cada doce meses de ejecución contractual, el canon mensual de arrendamiento se "
        "incrementará automáticamente de acuerdo con la variación del Índice de Precios al Consumidor (IPC) "
        "certificado por el DANE correspondiente al año inmediatamente anterior más dos puntos porcentuales (IPC + 2%).\n\n"
        "CLÁUSULA CUARTA. — SERVICIOS PÚBLICOS Y CUOTA DE ADMINISTRACIÓN: El pago correspondiente a los "
        "servicios públicos domiciliarios de energía eléctrica, agua potable, alcantarillado, aseo y telecomunicaciones "
        "será asumido de manera directa y exclusiva por LA ARRENDATARIA. La cuota de administración ordinaria "
        "del edificio, tasada a la fecha en la suma de UN MILLÓN DOSCIENTOS MIL PESOS ($ 1.200.000 COP), será "
        "igualmente sufragada por LA ARRENDATARIA oportunamente.",
        fontsize=10.5, fontname="helv", align=fitz.TEXT_ALIGN_JUSTIFY
    )

    # Page 3
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(fitz.Point(50, 60), "Contrato de Arrendamiento N° AR-2026-991 — Página 3 de 4", fontsize=8.5, fontname="helv", color=(0.5, 0.5, 0.5))

    p3.insert_textbox(
        fitz.Rect(50, 90, 545, 800),
        "CLÁUSULA QUINTA. — CLÁUSULA PENAL PECUNIARIA: En caso de incumplimiento de cualquiera de las "
        "obligaciones derivadas del presente contrato por parte de cualquiera de los contratantes, la parte "
        "incumplida pagará a la otra parte cumplida o que se haya allanado a cumplir, a título de pena, una "
        "suma equivalente a TRES (3) CÁNONES MENSUALES DE ARRENDAMIENTO vigentes al momento de la infracción, "
        "esto es, la suma de TREINTA Y SIETE MILLONES QUINIENTOS MIL PESOS M/CTE ($ 37.500.000 COP), "
        "sin perjuicio de las indemnizaciones por daños y perjuicios a que haya lugar de acuerdo con la ley.\n\n"
        "CLÁUSULA SEXTA. — DESTINACIÓN Y REFORMAS: LA ARRENDATARIA no podrá cambiar la destinación del inmueble "
        "sin previa autorización expresa y por escrito de EL ARRENDADOR, ni subarrendar total o parcialmente el local. "
        "Toda mejora o reforma que requiera realizar en el local requerirá aprobación previa por escrito.",
        fontsize=10.5, fontname="helv", align=fitz.TEXT_ALIGN_JUSTIFY
    )

    # Page 4 (Signatures page)
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text(fitz.Point(50, 60), "Contrato de Arrendamiento N° AR-2026-991 — Página 4 de 4", fontsize=8.5, fontname="helv", color=(0.5, 0.5, 0.5))

    p4.insert_textbox(
        fitz.Rect(50, 90, 545, 300),
        "En constancia de lo acordado y en señal de aceptación expresa y libre de vicios, se firma el presente "
        "documento en dos (2) ejemplares de idéntico tenor y valor legal, en la ciudad de Bogotá D.C., "
        "a los veintidós (22) días del mes de mayo del año dos mil veintiséis (2026).",
        fontsize=10.5, fontname="helv", align=fitz.TEXT_ALIGN_JUSTIFY
    )

    # Signature blocks
    shape = p4.new_shape()
    shape.draw_line(fitz.Point(70, 320), fitz.Point(260, 320))
    shape.draw_line(fitz.Point(320, 320), fitz.Point(510, 320))
    shape.finish(color=(0.2, 0.2, 0.2), width=1.0)
    shape.commit()

    p4.insert_text(fitz.Point(70, 335), "EL ARRENDADOR:", fontsize=9, fontname="helv")
    p4.insert_text(fitz.Point(70, 350), "ROBERTO ANTONIO JARAMILLO O.", fontsize=10, fontname="helv")
    p4.insert_text(fitz.Point(70, 365), "C.C. 79.432.890 de Bogotá", fontsize=9, fontname="helv")

    p4.insert_text(fitz.Point(320, 335), "LA ARRENDATARIA:", fontsize=9, fontname="helv")
    p4.insert_text(fitz.Point(320, 350), "VALERIA MONTOYA DUQUE", fontsize=10, fontname="helv")
    p4.insert_text(fitz.Point(320, 365), "Representante Legal - C.C. 52.981.442", fontsize=9, fontname="helv")
    p4.insert_text(fitz.Point(320, 380), "Comercializadora Alianza Global S.A.S.", fontsize=8.5, fontname="helv")

    doc.save(output_path)
    doc.close()


def create_mixto_sello_firma(output_path: Path):
    """Generates a document with digital native text plus visual graphics (stamps and signatures)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text(fitz.Point(140, 70), "CERTIFICACIÓN DE RECEPCIÓN Y LIQUIDACIÓN TÉCNICA", fontsize=12, fontname="helv")
    page.insert_text(fitz.Point(210, 90), "ACTA N° 045 - ALCALDÍA MAYOR", fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))

    page.insert_textbox(
        fitz.Rect(50, 120, 545, 380),
        "Por medio del presente documento se hace constar que el contratista INGENIERÍA Y REDES NACIONALES S.A.S. "
        "ha completado a entera satisfacción el 100% de las obras correspondientes al HITO 3 del Contrato de "
        "Obra Pública N° 410-2025. El valor liquidado asciende a la suma de CUARENTA Y SIETE MILLONES DOSCIENTOS "
        "MIL PESOS ($ 47.200.000 COP). Se expide el presente paz y salvo tras la revisión técnica de la interventoría.",
        fontsize=10.5, fontname="helv", align=fitz.TEXT_ALIGN_JUSTIFY
    )

    # Draw a simulated official circular stamp (Vector graphics in PDF)
    shape = page.new_shape()
    center = fitz.Point(160, 480)
    # Outer circle
    shape.draw_circle(center, 55)
    # Inner circle
    shape.draw_circle(center, 45)
    shape.finish(color=(0.8, 0.1, 0.1), width=1.5)
    shape.commit()

    # Stamp text
    page.insert_text(fitz.Point(125, 465), "ALCALDÍA MAYOR", fontsize=8.5, fontname="helv", color=(0.8, 0.1, 0.1))
    page.insert_text(fitz.Point(135, 480), "APROBADO", fontsize=10, fontname="helv", color=(0.8, 0.1, 0.1))
    page.insert_text(fitz.Point(122, 495), "INTERVENTORÍA", fontsize=8, fontname="helv", color=(0.8, 0.1, 0.1))

    # Draw simulated handwritten signature with vector bezier curve
    shape_sig = page.new_shape()
    shape_sig.draw_bezier(fitz.Point(340, 500), fitz.Point(370, 440), fitz.Point(400, 530), fitz.Point(450, 470))
    shape_sig.draw_bezier(fitz.Point(450, 470), fitz.Point(470, 450), fitz.Point(490, 520), fitz.Point(520, 490))
    shape_sig.draw_line(fitz.Point(330, 520), fitz.Point(530, 520))
    shape_sig.finish(color=(0.05, 0.15, 0.5), width=1.8)
    shape_sig.commit()

    page.insert_text(fitz.Point(350, 535), "ING. CARLOS ARTURO MÉNDEZ", fontsize=9, fontname="helv")
    page.insert_text(fitz.Point(350, 550), "Interventor Principal - Mat. 254921-CND", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))

    doc.save(output_path)
    doc.close()


def create_escaneo_limpio(output_path: Path):
    """Generates a pure raster scan with zero native digital text (Lane: NEEDS_AI)."""
    # Create base digital page in memory
    doc_temp = fitz.open()
    p = doc_temp.new_page(width=595, height=842)
    p.insert_text(fitz.Point(80, 100), "HISTORIA CLÍNICA DE INGRESO - URGENCIAS", fontsize=14, fontname="helv")
    p.insert_text(fitz.Point(80, 140), "PACIENTE: Jorge Enrique Restrepo Saldarriaga", fontsize=11, fontname="helv")
    p.insert_text(fitz.Point(80, 170), "DOCUMENTO DE IDENTIDAD: C.C. 15.394.201", fontsize=10, fontname="helv")
    p.insert_text(fitz.Point(80, 200), "FECHA DE ATENCIÓN: 2026-03-12 14:35", fontsize=10, fontname="helv")
    p.insert_text(fitz.Point(80, 240), "DIAGNÓSTICO PRINCIPAL: Traumatismo en tobillo derecho con esguince grado II.", fontsize=10.5, fontname="helv")
    p.insert_text(fitz.Point(80, 280), "TRATAMIENTO: Inmovilización con férula, analgésico y reposo absoluto por 15 días.", fontsize=10, fontname="helv")
    p.insert_text(fitz.Point(80, 320), "MÉDICO TRATANTE: Dra. Claudia Marcela Suárez - R.M. 08241", fontsize=10, fontname="helv")

    # Render to raster pixmap (simulate physical page scan at 150 DPI)
    pix = p.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    doc_temp.close()

    # Add subtle scanner noise using PIL
    pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
    # Apply slight paper texture / brightness variation
    enhancer = ImageDraw.Draw(pil_img)
    enhancer.rectangle([0, 0, pil_img.width, 15], fill=(245, 245, 242))

    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=80)
    buf.seek(0)

    # Embed raster image into a brand new PDF without text layer
    doc_final = fitz.open()
    p_final = doc_final.new_page(width=595, height=842)
    p_final.insert_image(p_final.rect, stream=buf.getvalue())
    doc_final.save(output_path)
    doc_final.close()


def create_escaneo_inclinado_skew(output_path: Path):
    """Generates a scanned PDF rotated by ~8.5 degrees to benchmark OpenCV Deskew."""
    # Create base digital page
    doc_temp = fitz.open()
    p = doc_temp.new_page(width=595, height=842)
    p.insert_text(fitz.Point(70, 110), "PÓLIZA DE SEGURO TODO RIESGO AUTOMÓVIL", fontsize=13, fontname="helv")
    p.insert_text(fitz.Point(70, 140), "COMPAÑÍA ASEGURADORA NACIONAL S.A.", fontsize=11, fontname="helv")
    p.insert_text(fitz.Point(70, 180), "NÚMERO DE PÓLIZA: POL-2026-88741", fontsize=10.5, fontname="helv")
    p.insert_text(fitz.Point(70, 210), "ASEGURADO: ANDRÉS FELIPE SALAZAR RAMÍREZ", fontsize=10, fontname="helv")
    p.insert_text(fitz.Point(70, 240), "PLACA DEL VEHÍCULO: ABC-892", fontsize=10, fontname="helv")
    p.insert_text(fitz.Point(70, 270), "VALOR ASEGURADO: $ 68.000.000 COP", fontsize=10.5, fontname="helv")
    p.insert_text(fitz.Point(70, 300), "PRIMA TOTAL ANUAL: $ 2.450.000 COP", fontsize=10.5, fontname="helv")
    p.insert_text(fitz.Point(70, 330), "VIGENCIA DESDE: 2026-01-01 HASTA: 2027-01-01", fontsize=10, fontname="helv")

    pix = p.get_pixmap(dpi=150)
    doc_temp.close()

    # Rotate with PIL by 8.5 degrees (simulate tilted scanner bed)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    rotated_img = pil_img.rotate(8.5, resample=Image.BICUBIC, expand=True, fillcolor=(250, 250, 250))

    buf = io.BytesIO()
    rotated_img.save(buf, format="JPEG", quality=82)
    buf.seek(0)

    # Embed skewed image
    doc_final = fitz.open()
    p_final = doc_final.new_page(width=595, height=842)
    p_final.insert_image(p_final.rect, stream=buf.getvalue())
    doc_final.save(output_path)
    doc_final.close()


def create_ocr_corrupto(output_path: Path):
    """
    Generates a PDF with corrupted text layer (replacement characters \\ufffd and zero spaces)
    to test the readability_score classifier and trigger fallback to NEEDS_AI.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Insert corrupt gibberish strings simulating bad OCR
    corrupt_lines = [
        "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd",
        "T0t@l\\x00\\x01\\x02P4g4r98500000000000000000000000000000000000000",
        "F3ch@\\ufffd\\ufffd20260430\\ufffd\x03\x04\x05\x06\x07\x08",
        "N1T9001234567890123456789012345678901234567890123456789",
        "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd",
        "Cl4usul4P3n4lIncumpl1m13nt0P3cuni4r10D0cT0k3nsC0rrupt0s",
    ] * 6

    y = 80
    for line in corrupt_lines:
        page.insert_text(fitz.Point(60, y), line, fontsize=9, fontname="helv", color=(0.2, 0.2, 0.2))
        y += 20

    doc.save(output_path)
    doc.close()


def create_multipage_stress_20p(output_path: Path):
    """
    Generates a 20-page stress test document (exact limit RV-006) with mixed
    digital and simulated scan pages.
    """
    doc = fitz.open()

    for p_num in range(1, 21):
        page = doc.new_page(width=595, height=842)
        page.insert_text(
            fitz.Point(50, 50),
            f"EXPEDIENTE CORPORATIVO UNIFICADO — PÁGINA {p_num} DE 20",
            fontsize=10, fontname="helv", color=(0.4, 0.4, 0.4)
        )

        if p_num % 5 == 0:
            # Simulated stamp / graphic page
            page.insert_text(fitz.Point(70, 120), f"ANEXO TÉCNICO #{p_num}: COMPROBANTE FORENSE", fontsize=13, fontname="helv")
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(100, 180, 500, 400))
            shape.finish(color=(0.8, 0.2, 0.2), fill=(1.0, 0.96, 0.96), width=1.5)
            shape.commit()
            page.insert_text(fitz.Point(140, 280), f"COPIA SELLADA Y VALIDADA EN PÁGINA {p_num}", fontsize=12, fontname="helv", color=(0.8, 0.2, 0.2))
        else:
            # Standard digital page with extractable entities
            page.insert_text(fitz.Point(70, 100), f"CAPÍTULO {p_num}: EJECUCIÓN PRESUPUESTAL Y SOPORTES", fontsize=12, fontname="helv")
            page.insert_textbox(
                fitz.Rect(70, 130, 525, 750),
                f"El presente folio {p_num} documenta las transacciones y obligaciones pactadas entre las partes. "
                f"Para los efectos legales de este capítulo, se certifica que el valor acumulado al corte de la página {p_num} "
                f"es de ${p_num * 1_250_000:,} COP. Las partes confirmaron la recepción de los entregables requeridos "
                f"sin objeción alguna. La vigencia del periodo auditado comprende desde el inicio del trimestre hasta la fecha actual.",
                fontsize=10, fontname="helv"
            )

    doc.save(output_path)
    doc.close()


def generate_all_fixtures(output_dir: Path):
    """Orchestrates generation of all test fixtures."""
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures = [
        ("digital_factura.pdf", create_digital_factura, "Digital limpia", "LOCAL", 1),
        ("digital_contrato.pdf", create_digital_contrato, "Contrato multi-página", "LOCAL", 4),
        ("mixto_sello_firma.pdf", create_mixto_sello_firma, "Digital + Sellos/Firmas", "NEEDS_AI (selectivo)", 1),
        ("escaneo_limpio.pdf", create_escaneo_limpio, "Escaneo raster puro", "NEEDS_AI", 1),
        ("escaneo_inclinado_skew.pdf", create_escaneo_inclinado_skew, "Escaneo rotado (Deskew)", "NEEDS_AI (OpenCV)", 1),
        ("ocr_corrupto.pdf", create_ocr_corrupto, "Capa OCR corrupta", "NEEDS_AI (Fallback)", 1),
        ("multipage_stress_20p.pdf", create_multipage_stress_20p, "Documento 20 páginas (límite)", "MIXTO (20 páginas)", 20),
    ]

    print("\n" + "=" * 80)
    print("🚀 GENERADOR DE FIXTURES PDF PARA PYDECTIVE")
    print(f"Directorio de destino: {output_dir.resolve()}")
    print("=" * 80)
    print(f"{'Archivo':<30} | {'Tipo / Escenario':<25} | {'Carril Previsto':<18} | {'Págs':<5} | {'Tamaño'}")
    print("-" * 80)

    for filename, generator_func, desc, lane, pages in fixtures:
        filepath = output_dir / filename
        generator_func(filepath)
        size_kb = filepath.stat().st_size / 1024
        print(f"{filename:<30} | {desc:<25} | {lane:<18} | {pages:<5} | {size_kb:.1f} KB")

    print("-" * 80)
    print(f"✅ Se generaron exitosamente {len(fixtures)} fixtures PDF en {output_dir}.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de PDFs de prueba para PyDective")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="tests/fixtures",
        help="Directorio donde se guardarán los archivos PDF generados (por defecto: tests/fixtures)",
    )
    args = parser.parse_args()
    generate_all_fixtures(Path(args.output_dir))
