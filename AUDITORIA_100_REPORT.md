# Informe de Auditoría Masiva: Suite de 100 Documentos Multi-Formato

> **Fecha:** 2026-09-23 22:59:43 | **Archivos Evaluados:** 100 | **Tiempo Total:** 24.55 s

---

## 1. Métricas Globales de Rendimiento y SLA

- **Tasa de Ingesta Exitosa (HTTP 200):** 100/100 (100.0%)
- **Precisión Global de Entidades:** 260/385 (67.5%)
- **Detección Forense de Elementos Visuales:** 25/60 (41.7%)
- **Latencia P50 (Mediana):** 32.48 ms
- **Latencia P95:** 939.19 ms

---

## 2. Diagnóstico de Anomalías y Truncamiento de Entidades

Se detectaron **15 documentos** con truncamiento o extracción incompleta de entidades personales:

- **doc_051_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'ROBERTO ANTONIO JARAMILLO OSPINA')
- **doc_052_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'VALERIA MONTOYA DUQUE')
- **doc_053_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
- **doc_054_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
- **doc_055_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'ALEJANDRO VALENCIA HENAO')
- **doc_056_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'DIANA PATRICIA CÁRDENAS BOTERO')
- **doc_057_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'JUAN GUILLERMO ZAPATA RIVERA')
- **doc_058_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'LAURA CRISTINA PEÑA CASTILLO')
- **doc_059_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'ANDRÉS FELIPE SALAZAR LONDOÑO')
- **doc_060_escaneo.pdf** (escaneo_vision):
  • notario: extrajo 'No detectado en el documento' (esperado 'GLORIA INÉS VELÁSQUEZ TORRES')
- **doc_087_contrato.docx** (ofimatico_docx):
  • representante legal: extrajo 'CARLOS EDUARDO RESTREPO MEJ¶A' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
- **doc_088_contrato.docx** (ofimatico_docx):
  • representante legal: extrajo 'MAR¶A CONSUELO G»MEZ «LVAREZ' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
- **doc_090_contrato.docx** (ofimatico_docx):
  • representante legal: extrajo 'DIANA PATRICIA C«RDENAS BOTERO' (esperado 'DIANA PATRICIA CÁRDENAS BOTERO')
- **doc_098_extracto.txt** (ofimatico_txt):
  • representante: extrajo 'CARLOS EDUARDO RESTREPO MEJ¶A' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
- **doc_099_extracto.txt** (ofimatico_txt):
  • representante: extrajo 'MAR¶A CONSUELO G»MEZ «LVAREZ' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')

---

## 3. Desglose de Desempeño por Formato y Categoría

| ID | Archivo | Ext | Categoría | Carril | Latencia (ms) | Aciertos | Estado |
|---|---|---|---|---|---|---|---|
| 1 | doc_001_contrato.pdf | .pdf | juridico | local | 2040.5 | 5/5 | ✅ OK |
| 2 | doc_002_contrato.pdf | .pdf | juridico | local | 25.75 | 5/5 | ✅ OK |
| 3 | doc_003_contrato.pdf | .pdf | juridico | local | 26.43 | 5/5 | ✅ OK |
| 4 | doc_004_contrato.pdf | .pdf | juridico | local | 24.29 | 5/5 | ✅ OK |
| 5 | doc_005_contrato.pdf | .pdf | juridico | local | 54.57 | 5/5 | ✅ OK |
| 6 | doc_006_contrato.pdf | .pdf | juridico | local | 55.5 | 5/5 | ✅ OK |
| 7 | doc_007_contrato.pdf | .pdf | juridico | local | 27.08 | 5/5 | ✅ OK |
| 8 | doc_008_contrato.pdf | .pdf | juridico | local | 28.22 | 5/5 | ✅ OK |
| 9 | doc_009_contrato.pdf | .pdf | juridico | local | 27.33 | 5/5 | ✅ OK |
| 10 | doc_010_contrato.pdf | .pdf | juridico | local | 28.49 | 5/5 | ✅ OK |
| 11 | doc_011_contrato.pdf | .pdf | juridico | local | 32.48 | 5/5 | ✅ OK |
| 12 | doc_012_contrato.pdf | .pdf | juridico | local | 30.22 | 5/5 | ✅ OK |
| 13 | doc_013_contrato.pdf | .pdf | juridico | local | 29.45 | 5/5 | ✅ OK |
| 14 | doc_014_contrato.pdf | .pdf | juridico | local | 28.09 | 5/5 | ✅ OK |
| 15 | doc_015_contrato.pdf | .pdf | juridico | local | 60.85 | 5/5 | ✅ OK |
| 16 | doc_016_contrato.pdf | .pdf | juridico | local | 57.01 | 5/5 | ✅ OK |
| 17 | doc_017_contrato.pdf | .pdf | juridico | local | 30.15 | 5/5 | ✅ OK |
| 18 | doc_018_contrato.pdf | .pdf | juridico | local | 28.38 | 5/5 | ✅ OK |
| 19 | doc_019_contrato.pdf | .pdf | juridico | local | 35.43 | 5/5 | ✅ OK |
| 20 | doc_020_contrato.pdf | .pdf | juridico | local | 31.03 | 5/5 | ✅ OK |
| 21 | doc_021_contrato.pdf | .pdf | juridico | local | 30.33 | 5/5 | ✅ OK |
| 22 | doc_022_contrato.pdf | .pdf | juridico | local | 28.02 | 5/5 | ✅ OK |
| 23 | doc_023_contrato.pdf | .pdf | juridico | local | 28.79 | 5/5 | ✅ OK |
| 24 | doc_024_contrato.pdf | .pdf | juridico | local | 28.75 | 5/5 | ✅ OK |
| 25 | doc_025_contrato.pdf | .pdf | juridico | local | 66.59 | 5/5 | ✅ OK |
| 26 | doc_026_factura.pdf | .pdf | financiero | local | 12.62 | 4/4 | ✅ OK |
| 27 | doc_027_factura.pdf | .pdf | financiero | local | 11.72 | 4/4 | ✅ OK |
| 28 | doc_028_factura.pdf | .pdf | financiero | local | 12.57 | 4/4 | ✅ OK |
| 29 | doc_029_factura.pdf | .pdf | financiero | local | 12.13 | 4/4 | ✅ OK |
| 30 | doc_030_factura.pdf | .pdf | financiero | local | 13.9 | 4/4 | ✅ OK |
| 31 | doc_031_factura.pdf | .pdf | financiero | local | 16.95 | 4/4 | ✅ OK |
| 32 | doc_032_factura.pdf | .pdf | financiero | local | 11.34 | 4/4 | ✅ OK |
| 33 | doc_033_factura.pdf | .pdf | financiero | local | 12.32 | 4/4 | ✅ OK |
| 34 | doc_034_factura.pdf | .pdf | financiero | local | 11.93 | 4/4 | ✅ OK |
| 35 | doc_035_factura.pdf | .pdf | financiero | local | 13.27 | 4/4 | ✅ OK |
| 36 | doc_036_factura.pdf | .pdf | financiero | local | 11.19 | 4/4 | ✅ OK |
| 37 | doc_037_factura.pdf | .pdf | financiero | local | 13.02 | 4/4 | ✅ OK |
| 38 | doc_038_factura.pdf | .pdf | financiero | local | 13.32 | 4/4 | ✅ OK |
| 39 | doc_039_factura.pdf | .pdf | financiero | local | 11.68 | 4/4 | ✅ OK |
| 40 | doc_040_factura.pdf | .pdf | financiero | local | 10.86 | 4/4 | ✅ OK |
| ... | (60 archivos más evaluados con éxito) | | | | | | |