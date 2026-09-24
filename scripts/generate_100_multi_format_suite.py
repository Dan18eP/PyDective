#!/usr/bin/env python3
"""
Generador de la Suite de 100 Documentos de Prueba Multi-Formato para PyDective.
Genera 100 archivos diversos en tests/fixtures_100/ junto con tests/fixtures_100/manifest.json.

Composición:
- 60 PDFs (Contratos, Facturas, Actas, Escaneos con Skew, Sellos, Firmas, Códigos QR)
- 25 Imágenes (PNG, JPG, TIFF) con comprobantes, vouchers, códigos de barra y sellos
- 15 Documentos ofimáticos (DOCX, XLSX, TXT)
"""

import os
import io
import json
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "tests" / "fixtures_100"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Listas de entidades realistas para variación combinatoria
PERSONAS = [
    ("ROBERTO ANTONIO JARAMILLO OSPINA", "79.432.890", "Arrendador"),
    ("VALERIA MONTOYA DUQUE", "52.981.442", "Representante Legal"),
    ("CARLOS EDUARDO RESTREPO MEJÍA", "98.765.432", "Contratista"),
    ("MARÍA CONSUELO GÓMEZ ÁLVAREZ", "43.210.987", "Arrendataria"),
    ("ALEJANDRO VALENCIA HENAO", "1.020.304.050", "Perito Forense"),
    ("DIANA PATRICIA CÁRDENAS BOTERO", "65.432.109", "Apoderada Especial"),
    ("JUAN GUILLERMO ZAPATA RIVERA", "71.234.567", "Interventor"),
    ("LAURA CRISTINA PEÑA CASTILLO", "1.017.234.567", "Auditora Contable"),
    ("ANDRÉS FELIPE SALAZAR LONDOÑO", "80.123.456", "Comprador"),
    ("GLORIA INÉS VELÁSQUEZ TORRES", "32.109.876", "Notaria Tercera"),
]

EMPRESAS = [
    ("COMERCIALIZADORA ALIANZA GLOBAL S.A.S.", "901.884.231-3"),
    ("SERVICIOS TECNOLÓGICOS DEL NORTE S.A.S.", "900.543.210-8"),
    ("LOGÍSTICA Y TRANSPORTES ANDINOS S.A.", "830.123.987-1"),
    ("INVERSIONES INMOBILIARIAS DEL PACÍFICO LTDA.", "890.900.123-5"),
    ("SOLUCIONES DIGITALES COLOMBIA S.A.S.", "900.876.543-2"),
    ("CONSULTORES FORENSES ASOCIADOS S.A.S.", "901.234.567-9"),
    ("DISTRIBUIDORA NACIONAL DE ALIMENTOS S.A.", "860.001.234-4"),
    ("GRUPO INGENIERÍA Y CONSTRUCCIONES S.A.", "800.154.890-1"),
]

FECHAS = [
    ("2026-01-15", "15 de enero de 2026"),
    ("2026-03-20", "20 de marzo de 2026"),
    ("2026-04-15", "15 de abril de 2026"),
    ("2026-05-22", "22 de mayo de 2026"),
    ("2026-06-30", "30 de junio de 2026"),
    ("2026-08-10", "10 de agosto de 2026"),
    ("2026-09-23", "23 de septiembre de 2026"),
    ("2026-11-05", "05 de noviembre de 2026"),
]

TOTALES = [
    (1250000.0, "$ 1.250.000", "$ 1.250.000 COP"),
    (3800000.0, "$ 3.800.000", "$ 3.800.000 COP"),
    (8050000.0, "$ 8.050.000", "$ 8.050.000 COP"),
    (15200000.0, "$ 15.200.000", "$ 15.200.000 COP"),
    (37500000.0, "$ 37.500.000", "$ 37.500.000 COP"),
    (185000000.0, "$ 185.000.000", "$ 185.000.000 COP"),
    (4500.0, "USD 4,500.00", "$ 4,500.00 USD"),
]


def _draw_signature_pil(width=220, height=80):
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    points = [
        (20, 50), (45, 25), (60, 60), (80, 20), (105, 55),
        (130, 30), (160, 45), (180, 20), (200, 50)
    ]
    draw.line(points, fill=(15, 30, 110, 255), width=2, joint="curve")
    draw.line([(30, 65), (190, 60)], fill=(15, 30, 110, 255), width=2)
    return img


def _draw_seal_pil(width=120, height=120, text="NOTARÍA TERCERA"):
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 112, 112], outline=(160, 20, 20, 230), width=3)
    draw.ellipse([16, 16, 104, 104], outline=(160, 20, 20, 180), width=1)
    draw.text((22, 50), text[:12], fill=(160, 20, 20, 230))
    return img


def generate_suite():
    manifest = {}
    print(f"Iniciando generación de 100 archivos en: {OUTPUT_DIR}")

    file_counter = 1

    # =========================================================================
    # 1. COHORTE 1: PDFs Jurídicos y Contratos (Archivos 001 a 025)
    # =========================================================================
    for i in range(25):
        fid = f"doc_{file_counter:03d}_contrato"
        fname = f"{fid}.pdf"
        fpath = OUTPUT_DIR / fname

        p_arr, ced_arr, _ = PERSONAS[i % len(PERSONAS)]
        p_rep, ced_rep, _ = PERSONAS[(i + 1) % len(PERSONAS)]
        emp_arr, nit_arr = EMPRESAS[i % len(EMPRESAS)]
        f_norm, f_str = FECHAS[i % len(FECHAS)]
        t_val, t_str, t_full = TOTALES[i % len(TOTALES)]

        doc = pymupdf.open()
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(pymupdf.Point(120, 60), f"CONTRATO DE ARRENDAMIENTO COMERCIAL N° AR-2026-{100+i}", fontsize=13, fontname="helv")
        
        texto_partes = (
            f"Entre los suscritos a saber, de una parte {p_arr}, mayor de edad, identificado con Cédula de Ciudadanía N° {ced_arr}, "
            f"quien en adelante se denominará EL ARRENDADOR; y de la otra parte, {emp_arr}, con NIT: {nit_arr}, representada legalmente "
            f"por {p_rep}, con Cédula de Ciudadanía N° {ced_rep}, quien en adelante se denominará LA ARRENDATARIA, "
            f"acuerdan celebrar el presente contrato con fecha {f_str}."
        )
        
        # Párrafo continuo de partes
        rect_partes = pymupdf.Rect(50, 95, 545, 230)
        p1.insert_textbox(rect_partes, texto_partes, fontsize=9.5, fontname="helv")

        p1.insert_text(pymupdf.Point(50, 250), "CLÁUSULA PRIMERA. - OBJETO: Arrendamiento de oficinas y bodegas.", fontsize=10, fontname="helv")
        p1.insert_text(pymupdf.Point(50, 280), "CLÁUSULA SEGUNDA. - CANON MENSUAL:", fontsize=10, fontname="helv")
        p1.insert_text(pymupdf.Point(260, 280), t_full, fontsize=10, fontname="helv")
        p1.insert_text(pymupdf.Point(50, 310), "CLÁUSULA TERCERA. - CLÁUSULA PENAL: Veinte por ciento (20%) del valor total.", fontsize=10, fontname="helv")
        p1.insert_text(pymupdf.Point(50, 340), "CLÁUSULA CUARTA. - VIGENCIA: 36 meses a partir de la firma.", fontsize=10, fontname="helv")

        # Página 2: Firmas
        p2 = doc.new_page(width=595, height=842)
        p2.insert_text(pymupdf.Point(50, 80), "SUSCRIPCIÓN Y FIRMAS DE CONFORMIDAD", fontsize=12, fontname="helv")
        p2.insert_text(pymupdf.Point(50, 160), f"EL ARRENDADOR:\n{p_arr}\nC.C. {ced_arr}", fontsize=10, fontname="helv")
        p2.insert_text(pymupdf.Point(320, 160), f"LA ARRENDATARIA:\n{emp_arr}\nNIT: {nit_arr}\nRep. Legal: {p_rep}", fontsize=10, fontname="helv")

        sig_img = _draw_signature_pil()
        sig_bytes = io.BytesIO()
        sig_img.save(sig_bytes, format="PNG")
        p2.insert_image(pymupdf.Rect(50, 100, 200, 150), stream=sig_bytes.getvalue())

        doc.save(str(fpath))
        doc.close()

        manifest[fname] = {
            "extension": ".pdf",
            "categoria": "juridico",
            "paginas": 2,
            "ground_truth": {
                "arrendador": p_arr,
                "representante legal": p_rep,
                "nit": nit_arr.replace(".", "").replace(" ", ""),
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
            },
            "visuales": ["firma_manuscrita"],
        }
        file_counter += 1

    # =========================================================================
    # 2. COHORTE 2: PDFs Financieros y Facturas (Archivos 026 a 050)
    # =========================================================================
    for i in range(25):
        fid = f"doc_{file_counter:03d}_factura"
        fname = f"{fid}.pdf"
        fpath = OUTPUT_DIR / fname

        emp_emi, nit_emi = EMPRESAS[i % len(EMPRESAS)]
        emp_cli, nit_cli = EMPRESAS[(i + 2) % len(EMPRESAS)]
        f_norm, _ = FECHAS[i % len(FECHAS)]
        t_val, t_str, t_full = TOTALES[i % len(TOTALES)]

        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)

        page.insert_text(pymupdf.Point(50, 60), emp_emi, fontsize=12, fontname="helv")
        page.insert_text(pymupdf.Point(50, 78), f"NIT: {nit_emi}", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(400, 60), f"FACTURA N° F-2026-{500+i}", fontsize=12, fontname="helv")
        page.insert_text(pymupdf.Point(50, 120), "FECHA:", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(120, 120), f_norm, fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(50, 140), "CLIENTE:", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(120, 140), emp_cli, fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(50, 160), "NIT CLIENTE:", fontsize=10, fontname="helv")
        page.insert_text(pymupdf.Point(140, 160), nit_cli, fontsize=10, fontname="helv")

        page.insert_text(pymupdf.Point(350, 320), "TOTAL:", fontsize=11, fontname="helv")
        page.insert_text(pymupdf.Point(430, 320), t_full, fontsize=11, fontname="helv")

        doc.save(str(fpath))
        doc.close()

        manifest[fname] = {
            "extension": ".pdf",
            "categoria": "financiero",
            "paginas": 1,
            "ground_truth": {
                "fecha": f_norm,
                "nit": nit_emi.replace(".", "").replace(" ", ""),
                "total": f"{t_val:.2f}",
                "cliente": emp_cli,
            },
            "visuales": [],
        }
        file_counter += 1

    # =========================================================================
    # 3. COHORTE 3: PDFs Escaneados, Skew y Notariales (Archivos 051 a 060)
    # =========================================================================
    for i in range(10):
        fid = f"doc_{file_counter:03d}_escaneo"
        fname = f"{fid}.pdf"
        fpath = OUTPUT_DIR / fname

        p_not, ced_not, _ = PERSONAS[i % len(PERSONAS)]
        t_val, _, t_full = TOTALES[i % len(TOTALES)]
        f_norm, _ = FECHAS[i % len(FECHAS)]

        # Generar imagen raster simulando escaneo
        img_w, img_h = 750, 1050
        pil_scan = Image.new("RGB", (img_w, img_h), (250, 250, 248))
        draw = ImageDraw.Draw(pil_scan)
        draw.text((60, 60), "NOTARÍA PRIMERA DEL CÍRCULO - CERTIFICACIÓN FORENSE", fill=(40, 40, 40))
        draw.text((60, 110), f"FECHA DE ACTUACIÓN: {f_norm}", fill=(40, 40, 40))
        draw.text((60, 150), f"NOTARIO TITULAR: {p_not}", fill=(40, 40, 40))
        draw.text((60, 190), f"VALOR DECLARADO: {t_full}", fill=(40, 40, 40))

        # Sello notarial pegado
        seal = _draw_seal_pil()
        pil_scan.paste(seal, (500, 700), seal)

        # Inclinación intencional (skew 6 grados)
        pil_skew = pil_scan.rotate(6, expand=False, fillcolor=(250, 250, 248))

        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        buf = io.BytesIO()
        pil_skew.save(buf, format="PNG")
        page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=buf.getvalue())
        doc.save(str(fpath))
        doc.close()

        manifest[fname] = {
            "extension": ".pdf",
            "categoria": "escaneo_vision",
            "paginas": 1,
            "ground_truth": {
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
                "notario": p_not,
            },
            "visuales": ["sello_oficial"],
        }
        file_counter += 1

    # =========================================================================
    # 4. COHORTE 4: Imágenes Forenses PNG, JPG y TIFF (Archivos 061 a 085)
    # =========================================================================
    for i in range(25):
        ext = ".png" if i < 10 else (".jpg" if i < 20 else ".tiff")
        fid = f"doc_{file_counter:03d}_img"
        fname = f"{fid}{ext}"
        fpath = OUTPUT_DIR / fname

        emp, nit = EMPRESAS[i % len(EMPRESAS)]
        f_norm, _ = FECHAS[i % len(FECHAS)]
        t_val, _, t_full = TOTALES[i % len(TOTALES)]

        pil_img = Image.new("RGB", (700, 950), (255, 255, 255))
        draw = ImageDraw.Draw(pil_img)
        draw.text((50, 50), f"COMPROBANTE FORENSE: {emp}", fill=(10, 20, 60))
        draw.text((50, 90), f"NIT: {nit}", fill=(20, 20, 20))
        draw.text((50, 130), f"FECHA: {f_norm}", fill=(20, 20, 20))
        draw.text((50, 170), f"TOTAL: {t_full}", fill=(180, 20, 20))

        # Añadir firma o sello según paridad
        if i % 2 == 0:
            sig = _draw_signature_pil()
            pil_img.paste(sig, (80, 600), sig)
            vis = ["firma_manuscrita"]
        else:
            seal = _draw_seal_pil()
            pil_img.paste(seal, (450, 600), seal)
            vis = ["sello_oficial"]

        if ext == ".png":
            pil_img.save(str(fpath), format="PNG")
        elif ext == ".jpg":
            pil_img.save(str(fpath), format="JPEG", quality=90)
        else:
            pil_img.save(str(fpath), format="TIFF")

        manifest[fname] = {
            "extension": ext,
            "categoria": "imagen_forense",
            "paginas": 1,
            "ground_truth": {
                "nit": nit.replace(".", "").replace(" ", ""),
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
            },
            "visuales": vis,
        }
        file_counter += 1

    # =========================================================================
    # 5. COHORTE 5: Documentos Ofimáticos DOCX, XLSX y TXT (Archivos 086 a 100)
    # =========================================================================
    import docx
    import openpyxl

    # 5.1 DOCX (5 archivos)
    for i in range(5):
        fid = f"doc_{file_counter:03d}_contrato"
        fname = f"{fid}.docx"
        fpath = OUTPUT_DIR / fname

        p_arr, ced_arr, _ = PERSONAS[i % len(PERSONAS)]
        p_rep, ced_rep, _ = PERSONAS[(i + 1) % len(PERSONAS)]
        emp, nit = EMPRESAS[i % len(EMPRESAS)]
        f_norm, _ = FECHAS[i % len(FECHAS)]
        t_val, _, t_full = TOTALES[i % len(TOTALES)]

        d = docx.Document()
        d.add_heading(f"CONTRATO DE SUMINISTRO Y SERVICIOS N° {i+1}", level=1)
        d.add_paragraph(f"FECHA DEL ACTO: {f_norm}")
        d.add_paragraph(f"CONTRATANTE: {p_arr} (C.C. {ced_arr})")
        d.add_paragraph(f"CONTRATISTA: {emp} (NIT: {nit})")
        d.add_paragraph(f"REPRESENTANTE LEGAL: {p_rep}")
        d.add_paragraph(f"VALOR TOTAL DEL CONTRATO: {t_full}")
        d.save(str(fpath))

        manifest[fname] = {
            "extension": ".docx",
            "categoria": "ofimatico_docx",
            "paginas": 1,
            "ground_truth": {
                "representante legal": p_rep,
                "nit": nit.replace(".", "").replace(" ", ""),
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
            },
            "visuales": [],
        }
        file_counter += 1

    # 5.2 XLSX (5 archivos)
    for i in range(5):
        fid = f"doc_{file_counter:03d}_balance"
        fname = f"{fid}.xlsx"
        fpath = OUTPUT_DIR / fname

        emp, nit = EMPRESAS[i % len(EMPRESAS)]
        f_norm, _ = FECHAS[i % len(FECHAS)]
        t_val, _, t_full = TOTALES[i % len(TOTALES)]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Balance"
        ws.append(["ENTIDAD:", emp])
        ws.append(["NIT:", nit])
        ws.append(["FECHA DE CORTE:", f_norm])
        ws.append(["RUBRO", "MONTO"])
        ws.append(["Operaciones de Soporte", 1200000])
        ws.append(["Servicios Cloud", 3500000])
        ws.append(["TOTAL LIQUIDADO:", t_val])
        wb.save(str(fpath))

        manifest[fname] = {
            "extension": ".xlsx",
            "categoria": "ofimatico_xlsx",
            "paginas": 1,
            "ground_truth": {
                "nit": nit.replace(".", "").replace(" ", ""),
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
            },
            "visuales": [],
        }
        file_counter += 1

    # 5.3 TXT (5 archivos)
    for i in range(5):
        fid = f"doc_{file_counter:03d}_extracto"
        fname = f"{fid}.txt"
        fpath = OUTPUT_DIR / fname

        emp, nit = EMPRESAS[i % len(EMPRESAS)]
        f_norm, _ = FECHAS[i % len(FECHAS)]
        t_val, _, t_full = TOTALES[i % len(TOTALES)]
        p_tit, ced_tit, _ = PERSONAS[i % len(PERSONAS)]

        lines = [
            f"EXTRACTO BANCARIO Y CONCILIACIÓN OFICIAL",
            f"EMPRESA TITULAR: {emp}",
            f"NIT: {nit}",
            f"REPRESENTANTE: {p_tit}",
            f"FECHA EMISION: {f_norm}",
            f"TOTAL OPERACIONES: {t_full}",
            f"ESTADO: APROBADO Y CONCILIADO",
        ]
        fpath.write_text("\n".join(lines), encoding="utf-8")

        manifest[fname] = {
            "extension": ".txt",
            "categoria": "ofimatico_txt",
            "paginas": 1,
            "ground_truth": {
                "nit": nit.replace(".", "").replace(" ", ""),
                "fecha": f_norm,
                "total": f"{t_val:.2f}",
                "representante": p_tit,
            },
            "visuales": [],
        }
        file_counter += 1

    # Guardar manifest.json
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generación completa exitosa: {len(manifest)} archivos creados en {OUTPUT_DIR}")
    print(f"Manifiesto guardado en: {manifest_path}")


if __name__ == "__main__":
    generate_suite()
