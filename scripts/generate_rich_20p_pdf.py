#!/usr/bin/env python3
"""
Generador de documento PDF ultra-completo de 20 páginas para PyDective.
Contiene texto nativo enriquecido, múltiples imágenes rasterizadas (gráficos, fotos, sellos, firmas, códigos QR y barras),
tablas vectoriales estilizadas, diagramas de arquitectura, metadatos y foliado formal continuo (1 a 20).
"""

import io
import math
import random
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def create_gradient_banner(width: int, height: int, start_color=(20, 35, 60), end_color=(40, 75, 120)) -> bytes:
    """Genera una imagen con degradado horizontal suave."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for x in range(width):
        r = int(start_color[0] + (end_color[0] - start_color[0]) * (x / width))
        g = int(start_color[1] + (end_color[1] - start_color[1]) * (x / width))
        b = int(start_color[2] + (end_color[2] - start_color[2]) * (x / width))
        draw.line([(x, 0), (x, height)], fill=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_corporate_logo() -> bytes:
    """Crea un logotipo corporativo moderno de alta resolución."""
    img = Image.new("RGBA", (400, 100), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Emblema geométrico / escudo
    draw.polygon([(20, 20), (70, 10), (90, 50), (70, 90), (20, 80)], fill=(30, 70, 140))
    draw.polygon([(30, 28), (65, 20), (80, 50), (65, 80), (30, 72)], fill=(50, 120, 220))
    draw.ellipse([(45, 40), (65, 60)], fill=(255, 255, 255))

    # Texto del logotipo
    draw.text((110, 25), "PYDECTIVE", fill=(20, 40, 90))
    draw.text((110, 55), "FORENSIC ANALYTICS & AUDIT", fill=(100, 115, 140))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_bar_chart_image() -> bytes:
    """Crea un gráfico de barras comparativo de ejecución presupuestal."""
    width, height = 500, 260
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    # Ejes
    draw.line([(60, 20), (60, 220), (470, 220)], fill=(100, 116, 139), width=2)

    # Líneas guía
    for y in [60, 110, 160, 210]:
        draw.line([(60, y), (470, y)], fill=(226, 232, 240), width=1)
        val = (220 - y) * 20
        draw.text((20, y - 8), f"${val}M", fill=(100, 116, 139))

    categorias = [("Q1", 120, 100), ("Q2", 150, 140), ("Q3", 190, 180), ("Q4", 210, 195)]
    x_base = 90
    bar_width = 35

    for label, real_val, pto_val in categorias:
        # Barra proyectada
        h_pto = int(pto_val * 0.75)
        draw.rectangle([(x_base, 220 - h_pto), (x_base + bar_width, 220)], fill=(148, 163, 184))

        # Barra real ejecutada
        h_real = int(real_val * 0.75)
        draw.rectangle([(x_base + bar_width + 5, 220 - h_real), (x_base + 2 * bar_width + 5, 220)], fill=(37, 99, 235))

        draw.text((x_base + 20, 230), label, fill=(30, 41, 59))
        x_base += 95

    # Leyenda
    draw.rectangle([(280, 25), (300, 37)], fill=(148, 163, 184))
    draw.text((310, 23), "Presupuestado", fill=(71, 85, 105))
    draw.rectangle([(390, 25), (410, 37)], fill=(37, 99, 235))
    draw.text((420, 23), "Ejecutado Real", fill=(71, 85, 105))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_pie_chart_image() -> bytes:
    """Crea un gráfico de pastel de distribución porcentual."""
    width, height = 400, 300
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Sectores: 45% (azul), 30% (verde), 15% (ámbar), 10% (rojo)
    bbox = [40, 40, 260, 260]
    draw.pieslice(bbox, start=0, end=162, fill=(37, 99, 235))       # 45%
    draw.pieslice(bbox, start=162, end=270, fill=(16, 185, 129))    # 30%
    draw.pieslice(bbox, start=270, end=324, fill=(245, 158, 11))    # 15%
    draw.pieslice(bbox, start=324, end=360, fill=(239, 68, 68))     # 10%

    # Leyenda
    legends = [
        ("Nómina y RRHH (45%)", (37, 99, 235)),
        ("Infraestructura (30%)", (16, 185, 129)),
        ("Licenciamiento (15%)", (245, 158, 11)),
        ("Imprevistos (10%)", (239, 68, 68)),
    ]
    y_leg = 70
    for text, col in legends:
        draw.rectangle([(290, y_leg), (305, y_leg + 15)], fill=col)
        draw.text((315, y_leg + 1), text, fill=(30, 41, 59))
        y_leg += 40

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_architecture_diagram_image() -> bytes:
    """Genera un diagrama esquemático de arquitectura e integración tecnológica."""
    width, height = 500, 240
    img = Image.new("RGB", (width, height), (241, 245, 249))
    draw = ImageDraw.Draw(img)

    # Bloques de componentes
    boxes = [
        ("Frontend SSR\nTailwind v4", 30, 40, 130, 110, (224, 231, 255), (67, 56, 202)),
        ("FastAPI Gateway\nOrquestador", 180, 40, 280, 110, (219, 234, 254), (30, 64, 175)),
        ("PyMuPDF Engine\nCarril LOCAL", 330, 20, 450, 75, (220, 252, 231), (22, 101, 52)),
        ("Gemini 2.0 Flash\nCarril NEEDS_AI", 330, 95, 465, 150, (254, 243, 199), (146, 64, 14)),
        ("L0/L1 Tiered Cache\n(orjson + LRU)", 180, 160, 300, 220, (243, 232, 255), (107, 33, 168)),
    ]

    for label, x1, y1, x2, y2, bg, stroke in boxes:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=6, fill=bg, outline=stroke, width=2)
        draw.text((x1 + 8, y1 + 10), label, fill=stroke)

    # Flechas conectores
    draw.line([(130, 75), (180, 75)], fill=(100, 116, 139), width=2)
    draw.line([(280, 55), (330, 45)], fill=(100, 116, 139), width=2)
    draw.line([(280, 85), (330, 120)], fill=(100, 116, 139), width=2)
    draw.line([(230, 110), (230, 160)], fill=(100, 116, 139), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_notarial_stamp_image() -> bytes:
    """Crea un sello notarial húmedo circular detallado."""
    size = 220
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    color = (180, 25, 25, 230)  # Tinta roja

    # Círculos concéntricos
    draw.ellipse([(10, 10), (210, 210)], outline=color, width=4)
    draw.ellipse([(18, 18), (202, 202)], outline=color, width=1)
    draw.ellipse([(35, 35), (185, 185)], outline=color, width=2)

    # Textos circulares simulados
    draw.text((45, 45), "* NOTARÍA 45 DE BOGOTÁ *", fill=color)
    draw.text((62, 75), "REPÚBLICA DE", fill=color)
    draw.text((68, 92), "COLOMBIA", fill=color)
    draw.text((58, 115), "AUTENTICADO", fill=color)
    draw.text((55, 135), "ACTA N° 2026-881", fill=color)
    draw.text((60, 155), "FOLIOS: 20 DE 20", fill=color)

    # Simular textura de tinta irregular
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_signature_image(seed: int = 1) -> bytes:
    """Genera una firma autógrafa caligráfica realista."""
    width, height = 300, 100
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ink_color = (15, 35, 110, 220)  # Tinta azul clásica

    random.seed(seed)
    # Trazos caligráficos continuos
    points = []
    x, y = 30, 50
    points.append((x, y))
    for _ in range(16):
        x += random.randint(10, 22)
        y += random.randint(-25, 25)
        y = max(15, min(height - 15, y))
        points.append((x, y))

    # Bucle largo característico de firma
    points.extend([(230, 20), (270, 70), (190, 85), (280, 80)])

    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=ink_color, width=random.choice([2, 3]))

    # Rúbrica inferior
    draw.line([(25, 88), (260, 85)], fill=ink_color, width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_qr_code_image() -> bytes:
    """Genera una representación visual de código QR de validación fiscal."""
    size = 140
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Marcadores de posición de las esquinas
    def draw_corner(cx, cy):
        draw.rectangle([(cx, cy), (cx + 36, cy + 36)], fill=(0, 0, 0))
        draw.rectangle([(cx + 6, cy + 6), (cx + 30, cy + 30)], fill=(255, 255, 255))
        draw.rectangle([(cx + 12, cy + 12), (cx + 24, cy + 24)], fill=(0, 0, 0))

    draw_corner(10, 10)
    draw_corner(94, 10)
    draw_corner(10, 94)

    # Patrón de datos pseudoaleatorio estructurado
    random.seed(42)
    for row in range(5, 23):
        for col in range(5, 23):
            if (row < 8 and (col < 8 or col > 15)) or (row > 15 and col < 8):
                continue
            if random.random() > 0.45:
                x = col * 6
                y = row * 6
                draw.rectangle([(x, y), (x + 5, y + 5)], fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_barcode_128_image() -> bytes:
    """Genera un código de barras 128 de radicación documental."""
    width, height = 300, 60
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    random.seed(12345)
    x = 20
    while x < width - 20:
        bar_w = random.choice([1, 2, 3, 4])
        draw.rectangle([(x, 5), (x + bar_w, 45)], fill=(0, 0, 0))
        x += bar_w + random.choice([1, 2, 3, 4])

    draw.text((70, 48), "* RAD-2026-EXP-904128 *", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_simulated_photo(title: str, subtitle: str) -> bytes:
    """Genera una imagen simulada de evidencia fotográfica con metadatos forenses."""
    width, height = 400, 220
    img = Image.new("RGB", (width, height), (220, 225, 230))
    draw = ImageDraw.Draw(img)

    # Fondo texturizado simulando instalación / equipo
    for y in range(0, height, 8):
        shade = 190 + int(25 * math.sin(y / 15.0))
        draw.line([(0, y), (width, y)], fill=(shade, shade + 5, shade + 10))

    # Marco de servidor / rack en perspectiva
    draw.rectangle([(60, 30), (340, 180)], outline=(50, 60, 75), fill=(40, 45, 55), width=3)
    # Leds e indicadores
    for row in range(50, 170, 25):
        draw.rectangle([(75, row), (325, row + 18)], fill=(65, 75, 90), outline=(90, 100, 120))
        draw.ellipse([(85, row + 5), (93, row + 13)], fill=(16, 185, 129))  # LED verde
        draw.ellipse([(100, row + 5), (108, row + 13)], fill=(59, 130, 246)) # LED azul

    # Banner inferior con metadatos fotográficos
    draw.rectangle([(0, 185), (width, height)], fill=(15, 23, 42))
    draw.text((15, 190), f"EVIDENCIA: {title}", fill=(241, 245, 249))
    draw.text((15, 203), f"GPS: 4°39'21.4\"N 74°04'18.2\"W  •  {subtitle}", fill=(148, 163, 184))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def add_page_decorations(page: fitz.Page, page_num: int, total_pages: int = 20):
    """Inserta encabezado, foliado y pie de página formal uniforme."""
    width = 595
    height = 842

    # Línea superior de encabezado
    shape = page.new_shape()
    shape.draw_line(fitz.Point(50, 45), fitz.Point(width - 50, 45))
    shape.finish(color=(0.7, 0.75, 0.8), width=0.8)
    shape.commit()

    page.insert_text(
        fitz.Point(50, 40),
        "EXPEDIENTE FORENSE N° EXP-2026-9041  •  AUDITORÍA INTEGRAL",
        fontsize=8,
        fontname="helv",
        color=(0.4, 0.45, 0.5)
    )
    page.insert_text(
        fitz.Point(width - 150, 40),
        "CONFIDENCIAL / RESERVADO",
        fontsize=8,
        fontname="helv",
        color=(0.7, 0.2, 0.2)
    )

    # Pie de página y foliado formal continuo
    shape_bot = page.new_shape()
    shape_bot.draw_line(fitz.Point(50, height - 40), fitz.Point(width - 50, height - 40))
    shape_bot.finish(color=(0.7, 0.75, 0.8), width=0.8)
    shape_bot.commit()

    page.insert_text(
        fitz.Point(50, height - 28),
        "Sistema Automatizado de Peritaje Documental — PyDective v2.2.0",
        fontsize=8,
        fontname="helv",
        color=(0.5, 0.5, 0.5)
    )
    page.insert_text(
        fitz.Point(width - 130, height - 28),
        f"Folio {page_num} de {total_pages}",
        fontsize=9,
        fontname="helv",
        color=(0.1, 0.2, 0.4)
    )


def generate_rich_20p_document(output_path: Path):
    """
    Genera el documento completo de 20 páginas con texto, tablas, imágenes,
    gráficos, sellos, firmas y códigos de validación.
    """
    doc = fitz.open()

    # =========================================================================
    # PÁGINA 1: PORTADA CORPORATIVA / CARÁTULA FORMAL
    # =========================================================================
    p1 = doc.new_page(width=595, height=842)
    banner_bytes = create_gradient_banner(595, 130, (15, 30, 65), (35, 70, 130))
    p1.insert_image(fitz.Rect(0, 0, 595, 130), stream=banner_bytes)

    logo_bytes = create_corporate_logo()
    p1.insert_image(fitz.Rect(50, 150, 250, 200), stream=logo_bytes)

    p1.insert_text(fitz.Point(50, 250), "REPORTE TÉCNICO Y EXPEDIENTE FORENSE", fontsize=13, fontname="helv", color=(0.2, 0.4, 0.8))
    p1.insert_textbox(
        fitz.Rect(50, 275, 545, 380),
        "AUDITORÍA INTEGRAL DE CONTRATACIÓN PÚBLICA, PERITAJE INFORMÁTICO Y EJECUCIÓN FINANCIERA",
        fontsize=22, fontname="helv", color=(0.1, 0.15, 0.3)
    )

    # Cuadro formal de metadatos
    shape = p1.new_shape()
    shape.draw_rect(fitz.Rect(50, 400, 545, 560))
    shape.finish(color=(0.2, 0.3, 0.5), fill=(0.96, 0.97, 1.0), width=1.5)
    shape.commit()

    meta_items = [
        ("NÚMERO DE EXPEDIENTE:", "EXP-2026-9041-AUD-NAL"),
        ("ENTIDAD CONTRATANTE:", "MINISTERIO DE TECNOLOGÍAS Y SERVICIOS DIGITALES"),
        ("CONTRATISTA AUDITADO:", "CONSORCIO INFRAESTRUCTURA ANDINA S.A.S."),
        ("NIT CONTRATISTA:", "901.884.219-4"),
        ("VALOR TOTAL AUDITADO:", "$185.000.000 COP"),
        ("FECHA DE CORTE Y DICTAMEN:", "2026-09-23"),
        ("PERITO PRINCIPAL:", "Dr. Alejandro Valencia Gómez (C.C. 79.432.109)"),
        ("NIVEL DE CLASIFICACIÓN:", "RESERVADO - SEGURIDAD DE LA INFORMACIÓN"),
    ]
    y_pos = 425
    for label, val in meta_items:
        p1.insert_text(fitz.Point(70, y_pos), label, fontsize=9, fontname="helv", color=(0.3, 0.35, 0.45))
        p1.insert_text(fitz.Point(235, y_pos), val, fontsize=9.5, fontname="helv", color=(0.1, 0.15, 0.25))
        y_pos += 16

    # Código de barras inferior
    barcode_bytes = create_barcode_128_image()
    p1.insert_image(fitz.Rect(147, 720, 447, 780), stream=barcode_bytes)
    add_page_decorations(p1, 1)

    # =========================================================================
    # PÁGINA 2: TABLA DE CONTENIDO Y RESUMEN EJECUTIVO
    # =========================================================================
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(fitz.Point(50, 80), "TABLA DE CONTENIDO DEL EXPEDIENTE", fontsize=16, fontname="helv", color=(0.1, 0.2, 0.4))

    toc_items = [
        ("Módulo I: Marco Contractual, Partes y Representación Legal", "Págs. 3 - 5"),
        ("Módulo II: Cronograma, Hitos de Avance y Arquitectura Técnica", "Págs. 6 - 8"),
        ("Módulo III: Verificación Forense, Catalogación de Firmas y Sellos", "Págs. 9 - 10"),
        ("Módulo IV: Soporte Tributario y Facturación Electrónica DIAN", "Págs. 11 - 13"),
        ("Módulo V: Análisis Presupuestal, Variaciones e Inspección de Red", "Págs. 14 - 15"),
        ("Módulo VI: Anexo Fotográfico, Certificaciones y Dictamen Pericial", "Págs. 16 - 20"),
    ]
    y_toc = 115
    for title, pages in toc_items:
        p2.insert_text(fitz.Point(60, y_toc), title, fontsize=10.5, fontname="helv")
        p2.insert_text(fitz.Point(460, y_toc), pages, fontsize=10, fontname="helv", color=(0.3, 0.3, 0.3))
        y_toc += 24

    p2.insert_text(fitz.Point(50, 290), "RESUMEN EJECUTIVO DEL DICTAMEN", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))
    p2.insert_textbox(
        fitz.Rect(50, 310, 545, 460),
        "El presente informe compendia los hallazgos técnicos, documentales y financieros del contrato estatal "
        "N° 450-2026 suscrito entre las partes para el suministro de infraestructura en la nube y consultoría forense. "
        "A lo largo de los 20 folios útiles que componen este expediente, se contrastan los documentos digitales nativos, "
        "la facturación validada ante la DIAN, las firmas autógrafas de los apoderados legales y el inventario fotográfico "
        "de los servidores desplegados en el centro de datos principal.",
        fontsize=10, fontname="helv"
    )

    # Insertar gráfico comparativo Q1-Q4
    bar_bytes = create_bar_chart_image()
    p2.insert_text(fitz.Point(50, 485), "COMPORTAMIENTO FINANCIERO TRIMESTRAL (REAL VS PRESUPUESTO)", fontsize=11, fontname="helv", color=(0.2, 0.3, 0.5))
    p2.insert_image(fitz.Rect(50, 500, 545, 750), stream=bar_bytes)
    add_page_decorations(p2, 2)

    # =========================================================================
    # PÁGINA 3: IDENTIFICACIÓN DE PARTES Y REPRESENTACIÓN LEGAL
    # =========================================================================
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(fitz.Point(50, 80), "CAPÍTULO 1: IDENTIFICACIÓN DE LAS PARTES CONTRATANTES", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    p3.insert_textbox(
        fitz.Rect(50, 105, 545, 230),
        "En la ciudad de Bogotá D.C., a los quince (15) días del mes de enero de 2026, comparecieron al perfeccionamiento "
        "del presente instrumento: por una parte, EL CONTRATANTE, MINISTERIO DE TECNOLOGÍAS Y SERVICIOS DIGITALES, "
        "identificado con NIT 800.198.345-2, representado legalmente por el Viceministro Dr. MAURICIO CÁRDENAS ROCHA; "
        "y por la otra, EL CONTRATISTA, CONSORCIO INFRAESTRUCTURA ANDINA S.A.S., identificado con NIT 901.884.219-4, "
        "representado legalmente por la Dra. MARÍA CONSUELO GÓMEZ ÁLVAREZ, identificada con Cédula de Ciudadanía N° 52.890.124.",
        fontsize=10, fontname="helv"
    )

    # Tabla de datos de las partes
    shape = p3.new_shape()
    shape.draw_rect(fitz.Rect(50, 240, 545, 420))
    shape.finish(color=(0.3, 0.4, 0.6), fill=(0.98, 0.99, 1.0), width=1)
    shape.commit()

    p3.insert_text(fitz.Point(70, 265), "PARÁMETRO DOCUMENTAL", fontsize=10, fontname="helv", color=(0.2, 0.3, 0.5))
    p3.insert_text(fitz.Point(260, 265), "VALOR ASIGNADO Y REGISTRADO", fontsize=10, fontname="helv", color=(0.2, 0.3, 0.5))

    partes_data = [
        ("Contratante", "Ministerio de Tecnologías y Servicios Digitales"),
        ("NIT Contratante", "800.198.345-2"),
        ("Representante Contratante", "Mauricio Cárdenas Rocha"),
        ("Contratista", "Consorcio Infraestructura Andina S.A.S."),
        ("NIT Contratista", "901.884.219-4"),
        ("Representante Contratista", "María Consuelo Gómez Álvarez"),
        ("Cédula Representante", "52.890.124 de Bogotá"),
        ("Matrícula Mercantil", "02984102-12 de Cámara de Comercio"),
    ]
    y_row = 295
    for p, v in partes_data:
        p3.insert_text(fitz.Point(70, y_row), p, fontsize=9.5, fontname="helv")
        p3.insert_text(fitz.Point(260, y_row), v, fontsize=9.5, fontname="helv", color=(0.1, 0.2, 0.4))
        y_row += 16

    add_page_decorations(p3, 3)

    # =========================================================================
    # PÁGINA 4: CLÁUSULAS FINANCIERAS Y PENALES
    # =========================================================================
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text(fitz.Point(50, 80), "CAPÍTULO 2: CLÁUSULAS ECONÓMICAS, CANON Y SANCIONES", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    clausulas = [
        ("CLÁUSULA PRIMERA — OBJETO CONTRACTUAL:",
         "El contratista se obliga a realizar la auditoría, aseguramiento técnico e implantación de defensas informáticas "
         "en los centros de cómputo del Contratante conforme a las especificaciones contenidas en el pliego de condiciones."),
        ("CLÁUSULA SEGUNDA — VALOR TOTAL DEL CONTRATO:",
         "El valor total pactado para la ejecución completa del objeto contractual corresponde a la suma fija de "
         "CIENTO OCHENTA Y CINCO MILLONES DE PESOS MONEDA CORRIENTE ($185.000.000 COP), IVA incluido."),
        ("CLÁUSULA TERCERA — CANON MENSUAL DE ARRENDAMIENTO DE PLATAFORMA:",
         "Las partes convienen un canon mensual por el uso de la infraestructura dedicada ascendente a "
         "QUINCE MILLONES CUATROCIENTOS DIECISÉIS MIL PESOS ($15.416.000 COP) pagaderos a mes vencido."),
        ("CLÁUSULA CUARTA — CLÁUSULA PENAL PECUNIARIA:",
         "En caso de declaratoria de incumplimiento total o parcial de las obligaciones estipuladas, la parte cumplida "
         "hará efectiva a título de pena pecuniaria la suma de TREINTA Y SIETE MILLONES DE PESOS ($37.000.000 COP), "
         "equivalente exactamente al veinte por ciento (20%) del valor total contractual."),
        ("CLÁUSULA QUINTA — DURACIÓN Y VIGENCIA:",
         "El término de ejecución del presente contrato será de DOCE (12) MESES contados a partir de la firma del acta de inicio."),
    ]
    y_c = 110
    for title, body in clausulas:
        p4.insert_text(fitz.Point(50, y_c), title, fontsize=10.5, fontname="helv", color=(0.15, 0.25, 0.45))
        y_c += 18
        p4.insert_textbox(fitz.Rect(50, y_c, 545, y_c + 70), body, fontsize=9.5, fontname="helv")
        y_c += 75

    add_page_decorations(p4, 4)

    # =========================================================================
    # PÁGINA 5: PÓLIZAS DE SEGURO Y GARANTÍAS CONTRACTUALES
    # =========================================================================
    p5 = doc.new_page(width=595, height=842)
    p5.insert_text(fitz.Point(50, 80), "CAPÍTULO 3: PÓLIZAS DE CUMPLIMIENTO Y AMPAROS", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    polizas = [
        ("Buen Manejo del Anticipo", "POL-2026-901", "SEGUROS DEL ESTADO S.A.", "$37.000.000 COP", "2026-01-15 al 2026-07-15"),
        ("Cumplimiento del Contrato", "POL-2026-902", "SEGUROS DEL ESTADO S.A.", "$37.000.000 COP", "2026-01-15 al 2027-01-15"),
        ("Calidad del Servicio", "POL-2026-903", "SEGUROS DEL ESTADO S.A.", "$37.000.000 COP", "2026-01-15 al 2027-07-15"),
        ("Salarios y Prestaciones", "POL-2026-904", "SEGUROS DEL ESTADO S.A.", "$18.500.000 COP", "2026-01-15 al 2029-01-15"),
        ("Responsabilidad Civil", "POL-2026-905", "LA PREVISORA SEGUROS", "$92.500.000 COP", "2026-01-15 al 2027-01-15"),
    ]
    # Encabezado tabla
    shape = p5.new_shape()
    shape.draw_rect(fitz.Rect(50, 110, 545, 140))
    shape.finish(color=(0.2, 0.3, 0.5), fill=(0.9, 0.93, 0.98), width=1)
    shape.commit()

    p5.insert_text(fitz.Point(60, 128), "Amparo", fontsize=9, fontname="helv")
    p5.insert_text(fitz.Point(190, 128), "Póliza N°", fontsize=9, fontname="helv")
    p5.insert_text(fitz.Point(260, 128), "Aseguradora", fontsize=9, fontname="helv")
    p5.insert_text(fitz.Point(375, 128), "Valor Asegurado", fontsize=9, fontname="helv")
    p5.insert_text(fitz.Point(460, 128), "Vigencia", fontsize=9, fontname="helv")

    y_pol = 160
    for amparo, pol, aseg, valor, vig in polizas:
        p5.insert_text(fitz.Point(60, y_pol), amparo, fontsize=8.5, fontname="helv")
        p5.insert_text(fitz.Point(190, y_pol), pol, fontsize=8.5, fontname="helv")
        p5.insert_text(fitz.Point(260, y_pol), aseg, fontsize=8, fontname="helv")
        p5.insert_text(fitz.Point(375, y_pol), valor, fontsize=8.5, fontname="helv", color=(0.1, 0.3, 0.6))
        p5.insert_text(fitz.Point(460, y_pol), vig, fontsize=7.5, fontname="helv")
        y_pol += 30

    add_page_decorations(p5, 5)

    # =========================================================================
    # PÁGINA 6: CRONOGRAMA DE HITOS Y GESTIÓN DE AVANCE
    # =========================================================================
    p6 = doc.new_page(width=595, height=842)
    p6.insert_text(fitz.Point(50, 80), "CAPÍTULO 4: CRONOGRAMA OPERATIVO Y CUMPLIMIENTO DE HITOS", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    p6.insert_textbox(
        fitz.Rect(50, 105, 545, 170),
        "El avance contractual fue supervisado por la interventoría mediante cortes de inspección periódicos. "
        "A continuación se presenta el consolidado de ejecución por fases técnicas, verificándose un cumplimiento "
        "ponderado acumulado del 94.8% frente a la línea base aprobada.",
        fontsize=10, fontname="helv"
    )

    # Tabla de hitos
    hitos = [
        ("Hito 1: Levantamiento de Arquitectura y Baseline", "100%", "2026-02-15", "APROBADO"),
        ("Hito 2: Aprovisionamiento de Hardware y Redes", "100%", "2026-03-30", "APROBADO"),
        ("Hito 3: Despliegue de Motores de Análisis Forense", "98%", "2026-05-15", "APROBADO"),
        ("Hito 4: Migración de Base de Datos y Certificación", "92%", "2026-07-30", "EN OBSERVACIÓN"),
        ("Hito 5: Pruebas de Carga, Penetración y Entrega Final", "89%", "2026-09-15", "EN EJECUCIÓN"),
    ]
    y_h = 200
    for h_name, pct, f_lim, status in hitos:
        p6.insert_text(fitz.Point(60, y_h), h_name, fontsize=9.5, fontname="helv")
        p6.insert_text(fitz.Point(340, y_h), pct, fontsize=10, fontname="helv", color=(0.1, 0.5, 0.2))
        p6.insert_text(fitz.Point(390, y_h), f_lim, fontsize=9, fontname="helv")
        p6.insert_text(fitz.Point(470, y_h), status, fontsize=9, fontname="helv", color=(0.8, 0.2, 0.2) if "OBSERV" in status else (0.1, 0.4, 0.7))
        y_h += 35

    add_page_decorations(p6, 6)

    # =========================================================================
    # PÁGINA 7: ARQUITECTURA TÉCNICA E INFOGRAFÍA DE SISTEMAS
    # =========================================================================
    p7 = doc.new_page(width=595, height=842)
    p7.insert_text(fitz.Point(50, 80), "CAPÍTULO 5: TOPOLOGÍA Y ARQUITECTURA DEL SISTEMA AUDITADO", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    diag_bytes = create_architecture_diagram_image()
    p7.insert_image(fitz.Rect(50, 110, 545, 360), stream=diag_bytes)

    p7.insert_textbox(
        fitz.Rect(50, 390, 545, 550),
        "El diagrama superior ilustra la infraestructura de alta disponibilidad implementada para PyDective. "
        "Los flujos de entrada son filtrados por el Gateway de FastAPI, el cual ejecuta la validación inicial en RAM "
        "(limitada a 25 MB y 20 páginas por documento según RV-006). A continuación, el motor de clasificación determina "
        "con precisión matemática si el documento discurre por el Carril Rápido LOCAL (resolución PyMuPDF C < 200 ms) "
        "o el Carril Asistido NEEDS_AI (Gemini 2.0 Flash con zero-thinking budget).",
        fontsize=10, fontname="helv"
    )

    add_page_decorations(p7, 7)

    # =========================================================================
    # PÁGINA 8: INSPECCIÓN EN SITIO Y REGISTRO DE SERIALES
    # =========================================================================
    p8 = doc.new_page(width=595, height=842)
    p8.insert_text(fitz.Point(50, 80), "CAPÍTULO 6: ACTA DE INSPECCIÓN FÍSICA EN DATA CENTER", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    photo_bytes = create_simulated_photo("RACK 04 - SERVIDORES DE IA", "CENTRO DE DATOS BOGOTÁ DC")
    p8.insert_image(fitz.Rect(95, 110, 495, 330), stream=photo_bytes)

    p8.insert_text(fitz.Point(50, 360), "INVENTARIO TÉCNICO DE ACTIVOS VERIFICADOS EN CAMPO", fontsize=11, fontname="helv", color=(0.2, 0.3, 0.5))

    activos = [
        ("SRV-01", "Servidor Cómputo Principal Dell PowerEdge R750", "SN-8849-XK01", "OPERACIONAL"),
        ("SRV-02", "Servidor de Inferencia Acelerada NVIDIA A100", "SN-9921-NV04", "OPERACIONAL"),
        ("STO-01", "Cabina de Almacenamiento NVMe All-Flash 120TB", "SN-3312-STO9", "OPERACIONAL"),
        ("SW-01", "Switch de Core Arista 100GbE Baja Latencia", "SN-1102-AR77", "OPERACIONAL"),
    ]
    y_act = 390
    for ref, desc, sn, st in activos:
        p8.insert_text(fitz.Point(60, y_act), ref, fontsize=9.5, fontname="helv", color=(0.2, 0.3, 0.5))
        p8.insert_text(fitz.Point(120, y_act), desc, fontsize=8.5, fontname="helv")
        p8.insert_text(fitz.Point(400, y_act), sn, fontsize=8.5, fontname="helv", color=(0.1, 0.3, 0.6))
        p8.insert_text(fitz.Point(480, y_act), st, fontsize=8.5, fontname="helv", color=(0.1, 0.5, 0.2))
        y_act += 30

    add_page_decorations(p8, 8)

    # =========================================================================
    # PÁGINA 9: CATALOGACIÓN DE FIRMAS Y RÚBRICAS AUTÓGRAFAS
    # =========================================================================
    p9 = doc.new_page(width=595, height=842)
    p9.insert_text(fitz.Point(50, 80), "CAPÍTULO 7: CATALOGACIÓN FORENSE DE FIRMAS Y REPRESENTACIÓN", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    p9.insert_textbox(
        fitz.Rect(50, 105, 545, 160),
        "Conforme al protocolo de aseguramiento documental (US-13), se levantó el catálogo de firmas autógrafas "
        "para el cotejo pericial de validez y verificación de autoría de los apoderados del contrato.",
        fontsize=10, fontname="helv"
    )

    # Firmas
    sig1 = create_signature_image(seed=101)
    p9.insert_image(fitz.Rect(70, 180, 270, 260), stream=sig1)
    p9.insert_text(fitz.Point(70, 275), "Dr. MAURICIO CÁRDENAS ROCHA", fontsize=10, fontname="helv")
    p9.insert_text(fitz.Point(70, 290), "Viceministro — Entidad Contratante", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    sig2 = create_signature_image(seed=202)
    p9.insert_image(fitz.Rect(320, 180, 520, 260), stream=sig2)
    p9.insert_text(fitz.Point(320, 275), "Dra. MARÍA CONSUELO GÓMEZ", fontsize=10, fontname="helv")
    p9.insert_text(fitz.Point(320, 290), "Representante Legal — Consorcio Andino", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    sig3 = create_signature_image(seed=303)
    p9.insert_image(fitz.Rect(195, 340, 395, 420), stream=sig3)
    p9.insert_text(fitz.Point(195, 435), "Ing. ALBERTO JARAMILLO DUQUE", fontsize=10, fontname="helv")
    p9.insert_text(fitz.Point(195, 450), "Interventor Principal del Proyecto", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    add_page_decorations(p9, 9)

    # =========================================================================
    # PÁGINA 10: SELLO NOTARIAL Y PROTOCOLO DE AUTENTICACIÓN
    # =========================================================================
    p10 = doc.new_page(width=595, height=842)
    p10.insert_text(fitz.Point(50, 80), "CAPÍTULO 8: ACTA NOTARIAL DE AUTENTICACIÓN Y RECONOCIMIENTO", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    stamp_bytes = create_notarial_stamp_image()
    p10.insert_image(fitz.Rect(185, 120, 405, 340), stream=stamp_bytes)

    p10.insert_textbox(
        fitz.Rect(50, 370, 545, 520),
        "El suscrito Notario Cuarenta y Cinco (45) del Círculo Notarial de Bogotá D.C., CERTIFICA: Que la firma y sello que "
        "anteceden corresponden a los registrados en esta dependencia, habiendo comparecido personalmente los otorgantes "
        "con exhibición de sus documentos de identidad idóneos, manifestando que reconocen como suyo el contenido íntegro "
        "del contrato, planos, anexos y tablas de liquidación adjuntos. Se expide copia auténtica en testimonio de lo actuado.",
        fontsize=10, fontname="helv"
    )

    add_page_decorations(p10, 10)

    # =========================================================================
    # PÁGINA 11: FACTURA ELECTRÓNICA PRINCIPAL (N° FE-2026-7890)
    # =========================================================================
    p11 = doc.new_page(width=595, height=842)
    p11.insert_text(fitz.Point(50, 75), "FACTURA ELECTRÓNICA DE VENTA N° FE-2026-7890", fontsize=15, fontname="helv", color=(0.1, 0.2, 0.4))

    # Bloque emisor y receptor
    shape = p11.new_shape()
    shape.draw_rect(fitz.Rect(50, 95, 545, 185))
    shape.finish(color=(0.2, 0.3, 0.5), fill=(0.97, 0.98, 1.0), width=1)
    shape.commit()

    p11.insert_text(fitz.Point(65, 115), "EMISOR: Consorcio Infraestructura Andina S.A.S.  •  NIT: 901.884.219-4", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(65, 130), "Dirección: Carrera 7 # 71-52 Torre B Piso 14, Bogotá D.C.", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))
    p11.insert_text(fitz.Point(65, 150), "ADQUIRIENTE: Ministerio de Tecnologías y Servicios Digitales  •  NIT: 800.198.345-2", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(65, 165), "Fecha de Emisión: 2026-04-30  •  Fecha de Vencimiento: 2026-05-30", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    # Detalle de ítems
    items = [
        ("01", "Servicios de Auditoría Forense y Peritaje Informático Mes 1", "$35.000.000", "$35.000.000"),
        ("02", "Canon de Almacenamiento en Nube Dedicada 120TB", "$15.000.000", "$15.000.000"),
    ]
    y_it = 220
    for cod, desc, vu, tot in items:
        p11.insert_text(fitz.Point(60, y_it), cod, fontsize=9, fontname="helv")
        p11.insert_text(fitz.Point(100, y_it), desc, fontsize=8.5, fontname="helv")
        p11.insert_text(fitz.Point(400, y_it), vu, fontsize=9, fontname="helv")
        p11.insert_text(fitz.Point(470, y_it), tot, fontsize=9, fontname="helv", color=(0.1, 0.2, 0.4))
        y_it += 30

    # Totales factura
    p11.insert_text(fitz.Point(360, 310), "SUBTOTAL:", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(460, 310), "$50.000.000 COP", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(360, 330), "IVA (19%):", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(460, 330), "$9.500.000 COP", fontsize=9.5, fontname="helv")
    p11.insert_text(fitz.Point(360, 355), "TOTAL FACTURA:", fontsize=11, fontname="helv", color=(0.8, 0.1, 0.1))
    p11.insert_text(fitz.Point(460, 355), "$59.500.000 COP", fontsize=12, fontname="helv", color=(0.8, 0.1, 0.1))

    # Código QR DIAN
    qr_bytes = create_qr_code_image()
    p11.insert_image(fitz.Rect(50, 380, 190, 520), stream=qr_bytes)
    p11.insert_text(fitz.Point(210, 420), "CUFE: a9b3c4d5e6f708192a3b4c5d6e7f80912a3b4c5d6e7f8a9b", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    p11.insert_text(fitz.Point(210, 440), "Validación previa DIAN autorizada con éxito.", fontsize=9, fontname="helv", color=(0.1, 0.5, 0.2))

    add_page_decorations(p11, 11)

    # =========================================================================
    # PÁGINA 12: FACTURA ELECTRÓNICA SECUNDARIA (N° FE-2026-7891)
    # =========================================================================
    p12 = doc.new_page(width=595, height=842)
    p12.insert_text(fitz.Point(50, 75), "FACTURA ELECTRÓNICA DE VENTA N° FE-2026-7891", fontsize=15, fontname="helv", color=(0.1, 0.2, 0.4))

    p12.insert_textbox(
        fitz.Rect(50, 105, 545, 175),
        "Concepto: Facturación correspondiente a la adquisición de licencias de peritaje automatizado PyDective Enterprise, "
        "soporte técnico especializado 24/7 y suscripción anual a bases de conocimiento forense.",
        fontsize=9.5, fontname="helv"
    )

    p12.insert_text(fitz.Point(360, 220), "SUBTOTAL:", fontsize=9.5, fontname="helv")
    p12.insert_text(fitz.Point(460, 220), "$25.000.000 COP", fontsize=9.5, fontname="helv")
    p12.insert_text(fitz.Point(360, 240), "IVA (19%):", fontsize=9.5, fontname="helv")
    p12.insert_text(fitz.Point(460, 240), "$4.750.000 COP", fontsize=9.5, fontname="helv")
    p12.insert_text(fitz.Point(360, 265), "TOTAL FACTURA:", fontsize=11, fontname="helv", color=(0.8, 0.1, 0.1))
    p12.insert_text(fitz.Point(460, 265), "$29.750.000 COP", fontsize=12, fontname="helv", color=(0.8, 0.1, 0.1))

    barcode2 = create_barcode_128_image()
    p12.insert_image(fitz.Rect(147, 400, 447, 460), stream=barcode2)

    add_page_decorations(p12, 12)

    # =========================================================================
    # PÁGINA 13: TABLA DE AMORTIZACIÓN Y DESEMBOLSOS
    # =========================================================================
    p13 = doc.new_page(width=595, height=842)
    p13.insert_text(fitz.Point(50, 80), "CAPÍTULO 9: TABLA DE DESEMBOLSOS Y AMORTIZACIÓN FINANCIERA", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    cuotas = [
        ("Mes 01", "$15.416.000", "$15.416.000", "$169.584.000", "PAGADO"),
        ("Mes 02", "$15.416.000", "$30.832.000", "$154.168.000", "PAGADO"),
        ("Mes 03", "$15.416.000", "$46.248.000", "$138.752.000", "PAGADO"),
        ("Mes 04", "$15.416.000", "$61.664.000", "$123.336.000", "PAGADO"),
        ("Mes 05", "$15.416.000", "$77.080.000", "$107.920.000", "PAGADO"),
        ("Mes 06", "$15.416.000", "$92.496.000", "$92.504.000", "PAGADO"),
        ("Mes 07", "$15.416.000", "$107.912.000", "$77.088.000", "PROGRAMADO"),
        ("Mes 08", "$15.416.000", "$123.328.000", "$61.672.000", "PROGRAMADO"),
    ]
    y_q = 130
    for m, c, acum, sal, st in cuotas:
        p13.insert_text(fitz.Point(60, y_q), m, fontsize=9.5, fontname="helv")
        p13.insert_text(fitz.Point(150, y_q), c, fontsize=9.5, fontname="helv")
        p13.insert_text(fitz.Point(260, y_q), acum, fontsize=9.5, fontname="helv", color=(0.1, 0.3, 0.6))
        p13.insert_text(fitz.Point(380, y_q), sal, fontsize=9.5, fontname="helv")
        p13.insert_text(fitz.Point(480, y_q), st, fontsize=9, fontname="helv", color=(0.1, 0.5, 0.2) if st == "PAGADO" else (0.8, 0.4, 0.1))
        y_q += 28

    add_page_decorations(p13, 13)

    # =========================================================================
    # PÁGINA 14: GRÁFICO CIRCULAR DE DISTRIBUCIÓN PRESUPUESTAL
    # =========================================================================
    p14 = doc.new_page(width=595, height=842)
    p14.insert_text(fitz.Point(50, 80), "CAPÍTULO 10: ESTRUCTURA DE COSTOS Y DISTRIBUCIÓN PORCENTUAL", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    pie_bytes = create_pie_chart_image()
    p14.insert_image(fitz.Rect(95, 120, 495, 420), stream=pie_bytes)

    p14.insert_textbox(
        fitz.Rect(50, 450, 545, 600),
        "El análisis pericial de costos demuestra que la mayor fracción presupuestal se concentra en el talento humano "
        "especializado en seguridad informática y análisis forense (45%), seguido por los gastos recurrentes de cómputo en la nube (30%). "
        "Los costos indirectos e imprevistos se mantuvieron estrictamente acotados dentro del margen de contingencia del 10%.",
        fontsize=10, fontname="helv"
    )

    add_page_decorations(p14, 14)

    # =========================================================================
    # PÁGINA 15: INFORME DE CIBERSEGURIDAD Y REGISTRO DE TRÁFICO
    # =========================================================================
    p15 = doc.new_page(width=595, height=842)
    p15.insert_text(fitz.Point(50, 80), "CAPÍTULO 11: AUDITORÍA DE TRÁFICO Y ANÁLISIS DE TELEMETRÍA", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    eventos = [
        ("EVT-001", "2026-04-12 03:14:22", "Escaneo de Puertos TCP Externo", "BAJA", "BLOQUEADO"),
        ("EVT-002", "2026-05-18 14:28:01", "Intento de Fuerza Bruta SSH Gateway", "MEDIA", "IP BAN 24H"),
        ("EVT-003", "2026-06-02 09:12:44", "Inyección SQL Sanitizada en API Form", "ALTA", "RECHAZADO"),
        ("EVT-004", "2026-07-20 22:50:11", "Tráfico Inusual en Bucket S3 Evidencias", "MEDIA", "AUDITADO"),
    ]
    y_ev = 120
    for cid, ts, desc, sev, accion in eventos:
        p15.insert_text(fitz.Point(60, y_ev), cid, fontsize=9.5, fontname="helv", color=(0.2, 0.3, 0.5))
        p15.insert_text(fitz.Point(120, y_ev), ts, fontsize=8.5, fontname="helv")
        p15.insert_text(fitz.Point(235, y_ev), desc, fontsize=8.5, fontname="helv")
        p15.insert_text(fitz.Point(420, y_ev), sev, fontsize=8.5, fontname="helv", color=(0.8, 0.2, 0.2) if sev == "ALTA" else (0.8, 0.5, 0.1))
        p15.insert_text(fitz.Point(480, y_ev), accion, fontsize=8.5, fontname="helv", color=(0.1, 0.5, 0.2))
        y_ev += 30

    add_page_decorations(p15, 15)

    # =========================================================================
    # PÁGINA 16: ANEXO FOTOGRÁFICO 1 (SERVIDORES Y CENTRO DE CÓMPUTO)
    # =========================================================================
    p16 = doc.new_page(width=595, height=842)
    p16.insert_text(fitz.Point(50, 80), "ANEXO FOTOGRÁFICO 1: INSPECCIÓN DE INFRAESTRUCTURA", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    f1 = create_simulated_photo("SALA DE CÓMPUTO - RACK PRINCIPAL", "TEMPERATURA 19°C — ACTA DE VISITA")
    p16.insert_image(fitz.Rect(95, 110, 495, 330), stream=f1)

    f2 = create_simulated_photo("SISTEMA DE RESPALDO ENERGÉTICO UPS", "AUTONOMÍA 4 HORAS — PRUEBA DE CARGA")
    p16.insert_image(fitz.Rect(95, 360, 495, 580), stream=f2)

    add_page_decorations(p16, 16)

    # =========================================================================
    # PÁGINA 17: ANEXO FOTOGRÁFICO 2 (DOCUMENTACIÓN Y LIBROS FÍSICOS)
    # =========================================================================
    p17 = doc.new_page(width=595, height=842)
    p17.insert_text(fitz.Point(50, 80), "ANEXO FOTOGRÁFICO 2: EXPEDIENTES Y ARCHIVO FÍSICO", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    f3 = create_simulated_photo("CARPETA DE RADICACIÓN N° 450-2026", "CADENA DE CUSTODIA PRESERVADA")
    p17.insert_image(fitz.Rect(95, 110, 495, 330), stream=f3)

    p17.insert_textbox(
        fitz.Rect(50, 360, 545, 500),
        "Se deja expresa constancia de que los documentos físicos reposan en la bóveda de seguridad ignífuga "
        "de la entidad contratante, debidamente rotulados y custodiados con precintos numerados de seguridad.",
        fontsize=10, fontname="helv"
    )

    add_page_decorations(p17, 17)

    # =========================================================================
    # PÁGINA 18: CERTIFICACIÓN BANCARIA DE FONDOS
    # =========================================================================
    p18 = doc.new_page(width=595, height=842)
    p18.insert_text(fitz.Point(50, 80), "CERTIFICACIÓN BANCARIA Y SOLVENCIA ECONÓMICA", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    shape = p18.new_shape()
    shape.draw_rect(fitz.Rect(50, 110, 545, 350))
    shape.finish(color=(0.2, 0.3, 0.5), fill=(0.98, 0.99, 1.0), width=1)
    shape.commit()

    p18.insert_text(fitz.Point(70, 140), "BANCO COMERCIAL COLOMBIANO S.A.  •  NIT 860.002.964-4", fontsize=11, fontname="helv", color=(0.1, 0.2, 0.4))
    p18.insert_textbox(
        fitz.Rect(70, 165, 525, 330),
        "A QUIEN PUEDA INTERESAR: El Banco certifica que el CONSORCIO INFRAESTRUCTURA ANDINA S.A.S., "
        "identificado con NIT 901.884.219-4, es titular de la cuenta corriente N° 450-981240-11, abierta el 12 de enero de 2024, "
        "la cual a la fecha presenta un manejo crediticio excelente y saldos acordes con la ejecución de contratos estatales. "
        "Se expide la presente en Bogotá D.C. a solicitud de la parte interesada.",
        fontsize=10, fontname="helv"
    )

    sig_bank = create_signature_image(seed=555)
    p18.insert_image(fitz.Rect(195, 370, 395, 450), stream=sig_bank)
    p18.insert_text(fitz.Point(210, 465), "GERENCIA DE BANCA INSTITUCIONAL", fontsize=9.5, fontname="helv")

    add_page_decorations(p18, 18)

    # =========================================================================
    # PÁGINA 19: CONCLUSIONES Y DICTAMEN PERICIAL
    # =========================================================================
    p19 = doc.new_page(width=595, height=842)
    p19.insert_text(fitz.Point(50, 80), "DICTAMEN PERICIAL FORENSE Y CONCLUSIONES", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    dictamenes = [
        ("1. AUTENTICIDAD DE DOCUMENTOS DIGITALES:",
         "El 100% de los documentos electrónicos analizados cuentan con firmas digitales válidas, "
         "metadatos íntegros y trazabilidad completa según la Ley 527 de 1999."),
        ("2. COHERENCIA DE LA FACTURACIÓN ELECTRÓNICA:",
         "Las facturas N° FE-2026-7890 y FE-2026-7891 coinciden exactamente con los montos presupuestados, "
         "los registros de desembolsos bancarios y los reportes de la DIAN."),
        ("3. CORRESPONDENCIA FÍSICA DE INFRAESTRUCTURA:",
         "Se comprobó en sitio la existencia real, operación continua y seriales de los equipos servidores "
         "declarados en los contratos y anexos técnicos."),
        ("4. DICTAMEN FINAL CATEGÓRICO:",
         "NO SE ENCONTRARON EVIDENCIAS DE FRAUDE, SOBRECOSTOS NI INCONSISTENCIAS en el expediente analizado. "
         "El peritaje declara CONFORMIDAD TÉCNICA Y FINANCIERA TOTAL."),
    ]
    y_dic = 115
    for tit, bod in dictamenes:
        p19.insert_text(fitz.Point(50, y_dic), tit, fontsize=10.5, fontname="helv", color=(0.15, 0.25, 0.45))
        y_dic += 18
        p19.insert_textbox(fitz.Rect(50, y_dic, 545, y_dic + 60), bod, fontsize=9.5, fontname="helv")
        y_dic += 65

    add_page_decorations(p19, 19)

    # =========================================================================
    # PÁGINA 20: DILIGENCIA DE CIERRE, FIRMAS FINALES Y HASH DE INTEGRIDAD
    # =========================================================================
    p20 = doc.new_page(width=595, height=842)
    p20.insert_text(fitz.Point(50, 80), "DILIGENCIA DE CIERRE Y SUSCRIPCIÓN DEL EXPEDIENTE", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.4))

    p20.insert_textbox(
        fitz.Rect(50, 105, 545, 175),
        "En constancia de lo anterior y para todos los efectos legales, se cierra formalmente el presente expediente "
        "contentivo de veinte (20) folios útiles y verificados. Las partes intervinientes ratifican el contenido "
        "y suscriben el documento a continuación.",
        fontsize=10, fontname="helv"
    )

    # 3 bloques de firmas y rúbricas
    s_f1 = create_signature_image(seed=701)
    p20.insert_image(fitz.Rect(60, 200, 240, 270), stream=s_f1)
    p20.insert_text(fitz.Point(60, 280), "Dr. MAURICIO CÁRDENAS", fontsize=9.5, fontname="helv")
    p20.insert_text(fitz.Point(60, 295), "Por el Contratante", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    s_f2 = create_signature_image(seed=702)
    p20.insert_image(fitz.Rect(350, 200, 530, 270), stream=s_f2)
    p20.insert_text(fitz.Point(350, 280), "Dra. MARÍA CONSUELO GÓMEZ", fontsize=9.5, fontname="helv")
    p20.insert_text(fitz.Point(350, 295), "Por el Contratista", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    s_f3 = create_signature_image(seed=703)
    p20.insert_image(fitz.Rect(205, 340, 385, 410), stream=s_f3)
    p20.insert_text(fitz.Point(205, 420), "Dr. ALEJANDRO VALENCIA GÓMEZ", fontsize=9.5, fontname="helv")
    p20.insert_text(fitz.Point(205, 435), "Perito Forense Oficial", fontsize=8.5, fontname="helv", color=(0.4, 0.4, 0.4))

    # Sello notarial en página final
    final_stamp = create_notarial_stamp_image()
    p20.insert_image(fitz.Rect(380, 480, 530, 630), stream=final_stamp)

    # Hash criptográfico de integridad
    shape = p20.new_shape()
    shape.draw_rect(fitz.Rect(50, 660, 545, 730))
    shape.finish(color=(0.2, 0.3, 0.5), fill=(0.95, 0.96, 0.98), width=1)
    shape.commit()

    p20.insert_text(fitz.Point(65, 680), "CERTIFICADO DE INTEGRIDAD DIGITAL SHA-256:", fontsize=8.5, fontname="helv", color=(0.2, 0.3, 0.5))
    p20.insert_text(fitz.Point(65, 700), "8f4a2c91e0d35b7a19284756c0b3a4a94affbcb862fbc43d4abd04450d80b8d672", fontsize=8, fontname="courier", color=(0.1, 0.1, 0.1))
    p20.insert_text(fitz.Point(65, 718), "Documento de 20 páginas foliadas, autenticado conforme a la norma ISO/IEC 27037.", fontsize=8, fontname="helv", color=(0.3, 0.5, 0.3))

    add_page_decorations(p20, 20)

    # =========================================================================
    # GUARDAR DOCUMENTO FINAL
    # =========================================================================
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path), deflate=True)
    doc.close()
    print(f"✅ Documento de 20 páginas generado exitosamente en: {output_path.resolve()}")


if __name__ == "__main__":
    out = Path("documento_completo_20_paginas.pdf")
    generate_rich_20p_document(out)
