# Informe de Auditoría Masiva: Suite de 100 Documentos Multi-Formato

> **Fecha:** 2026-09-23 22:39:21 | **Archivos Evaluados:** 100 | **Tiempo Total:** 28.35 s

---

## 1. Métricas Globales de Rendimiento y SLA

- **Tasa de Ingesta Exitosa (HTTP 200):** 100/100 (100.0%)
- **Precisión Global de Entidades:** 135/385 (35.1%)
- **Detección Forense de Elementos Visuales:** 25/60 (41.7%)
- **Latencia P50 (Mediana):** 27.15 ms
- **Latencia P95:** 994.36 ms

---

## 2. Diagnóstico de Anomalías y Truncamiento de Entidades

Se detectaron **65 documentos** con truncamiento o extracción incompleta de entidades personales:

- **doc_001_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'ROBERTO ANTONIO JARAMILLO OSPINA')
  • representante legal: extrajo 'VALERIA' (esperado 'VALERIA MONTOYA DUQUE')
- **doc_002_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'VALERIA MONTOYA DUQUE')
  • representante legal: extrajo 'CARLOS EDUARDO' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
- **doc_003_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
  • representante legal: extrajo 'MARÍA' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
- **doc_004_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
  • representante legal: extrajo 'por' (esperado 'ALEJANDRO VALENCIA HENAO')
- **doc_005_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'ALEJANDRO VALENCIA HENAO')
  • representante legal: extrajo 'DIANA' (esperado 'DIANA PATRICIA CÁRDENAS BOTERO')
- **doc_006_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'DIANA PATRICIA CÁRDENAS BOTERO')
  • representante legal: extrajo 'JUAN' (esperado 'JUAN GUILLERMO ZAPATA RIVERA')
- **doc_007_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'JUAN GUILLERMO ZAPATA RIVERA')
  • representante legal: extrajo 'LAURA' (esperado 'LAURA CRISTINA PEÑA CASTILLO')
- **doc_008_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'LAURA CRISTINA PEÑA CASTILLO')
  • representante legal: extrajo 'ANDRÉS' (esperado 'ANDRÉS FELIPE SALAZAR LONDOÑO')
- **doc_009_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'ANDRÉS FELIPE SALAZAR LONDOÑO')
  • representante legal: extrajo 'GLORIA' (esperado 'GLORIA INÉS VELÁSQUEZ TORRES')
- **doc_010_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'GLORIA INÉS VELÁSQUEZ TORRES')
  • representante legal: extrajo 'por' (esperado 'ROBERTO ANTONIO JARAMILLO OSPINA')
- **doc_011_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'ROBERTO ANTONIO JARAMILLO OSPINA')
  • representante legal: extrajo 'VALERIA' (esperado 'VALERIA MONTOYA DUQUE')
- **doc_012_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'VALERIA MONTOYA DUQUE')
  • representante legal: extrajo 'CARLOS EDUARDO' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
- **doc_013_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'CARLOS EDUARDO RESTREPO MEJÍA')
  • representante legal: extrajo 'MARÍA' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
- **doc_014_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'MARÍA CONSUELO GÓMEZ ÁLVAREZ')
  • representante legal: extrajo 'por' (esperado 'ALEJANDRO VALENCIA HENAO')
- **doc_015_contrato.pdf** (juridico):
  • arrendador: extrajo 'No detectado en el documento' (esperado 'ALEJANDRO VALENCIA HENAO')
  • representante legal: extrajo 'DIANA' (esperado 'DIANA PATRICIA CÁRDENAS BOTERO')
- ... y 50 documentos adicionales con anomalías similares.

---

## 3. Desglose de Desempeño por Formato y Categoría

| ID | Archivo | Ext | Categoría | Carril | Latencia (ms) | Aciertos | Estado |
|---|---|---|---|---|---|---|---|
| 1 | doc_001_contrato.pdf | .pdf | juridico | local | 2092.76 | 1/5 | ⚠️ Parcial |
| 2 | doc_002_contrato.pdf | .pdf | juridico | local | 23.37 | 1/5 | ⚠️ Parcial |
| 3 | doc_003_contrato.pdf | .pdf | juridico | local | 25.23 | 1/5 | ⚠️ Parcial |
| 4 | doc_004_contrato.pdf | .pdf | juridico | local | 27.15 | 1/5 | ⚠️ Parcial |
| 5 | doc_005_contrato.pdf | .pdf | juridico | local | 50.57 | 1/5 | ⚠️ Parcial |
| 6 | doc_006_contrato.pdf | .pdf | juridico | local | 48.7 | 1/5 | ⚠️ Parcial |
| 7 | doc_007_contrato.pdf | .pdf | juridico | local | 22.49 | 1/5 | ⚠️ Parcial |
| 8 | doc_008_contrato.pdf | .pdf | juridico | local | 22.89 | 1/5 | ⚠️ Parcial |
| 9 | doc_009_contrato.pdf | .pdf | juridico | local | 21.89 | 1/5 | ⚠️ Parcial |
| 10 | doc_010_contrato.pdf | .pdf | juridico | local | 22.46 | 1/5 | ⚠️ Parcial |
| 11 | doc_011_contrato.pdf | .pdf | juridico | local | 23.05 | 1/5 | ⚠️ Parcial |
| 12 | doc_012_contrato.pdf | .pdf | juridico | local | 22.12 | 1/5 | ⚠️ Parcial |
| 13 | doc_013_contrato.pdf | .pdf | juridico | local | 22.37 | 1/5 | ⚠️ Parcial |
| 14 | doc_014_contrato.pdf | .pdf | juridico | local | 22.42 | 1/5 | ⚠️ Parcial |
| 15 | doc_015_contrato.pdf | .pdf | juridico | local | 49.95 | 1/5 | ⚠️ Parcial |
| 16 | doc_016_contrato.pdf | .pdf | juridico | local | 47.68 | 1/5 | ⚠️ Parcial |
| 17 | doc_017_contrato.pdf | .pdf | juridico | local | 26.8 | 1/5 | ⚠️ Parcial |
| 18 | doc_018_contrato.pdf | .pdf | juridico | local | 22.99 | 1/5 | ⚠️ Parcial |
| 19 | doc_019_contrato.pdf | .pdf | juridico | local | 23.1 | 1/5 | ⚠️ Parcial |
| 20 | doc_020_contrato.pdf | .pdf | juridico | local | 22.28 | 1/5 | ⚠️ Parcial |
| 21 | doc_021_contrato.pdf | .pdf | juridico | local | 21.93 | 1/5 | ⚠️ Parcial |
| 22 | doc_022_contrato.pdf | .pdf | juridico | local | 24.46 | 1/5 | ⚠️ Parcial |
| 23 | doc_023_contrato.pdf | .pdf | juridico | local | 22.59 | 1/5 | ⚠️ Parcial |
| 24 | doc_024_contrato.pdf | .pdf | juridico | local | 22.99 | 1/5 | ⚠️ Parcial |
| 25 | doc_025_contrato.pdf | .pdf | juridico | local | 51.33 | 1/5 | ⚠️ Parcial |
| 26 | doc_026_factura.pdf | .pdf | financiero | local | 10.8 | 3/4 | ⚠️ Parcial |
| 27 | doc_027_factura.pdf | .pdf | financiero | local | 9.98 | 3/4 | ⚠️ Parcial |
| 28 | doc_028_factura.pdf | .pdf | financiero | local | 10.2 | 3/4 | ⚠️ Parcial |
| 29 | doc_029_factura.pdf | .pdf | financiero | local | 9.84 | 3/4 | ⚠️ Parcial |
| 30 | doc_030_factura.pdf | .pdf | financiero | local | 10.67 | 3/4 | ⚠️ Parcial |
| 31 | doc_031_factura.pdf | .pdf | financiero | local | 9.52 | 3/4 | ⚠️ Parcial |
| 32 | doc_032_factura.pdf | .pdf | financiero | local | 9.32 | 3/4 | ⚠️ Parcial |
| 33 | doc_033_factura.pdf | .pdf | financiero | local | 10.35 | 3/4 | ⚠️ Parcial |
| 34 | doc_034_factura.pdf | .pdf | financiero | local | 11.81 | 3/4 | ⚠️ Parcial |
| 35 | doc_035_factura.pdf | .pdf | financiero | local | 10.09 | 3/4 | ⚠️ Parcial |
| 36 | doc_036_factura.pdf | .pdf | financiero | local | 15.64 | 3/4 | ⚠️ Parcial |
| 37 | doc_037_factura.pdf | .pdf | financiero | local | 13.58 | 3/4 | ⚠️ Parcial |
| 38 | doc_038_factura.pdf | .pdf | financiero | local | 12.73 | 3/4 | ⚠️ Parcial |
| 39 | doc_039_factura.pdf | .pdf | financiero | local | 10.28 | 3/4 | ⚠️ Parcial |
| 40 | doc_040_factura.pdf | .pdf | financiero | local | 10.61 | 3/4 | ⚠️ Parcial |
| ... | (60 archivos más evaluados con éxito) | | | | | | |