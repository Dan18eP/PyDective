# Changelog: 25-09-2026

- Friday-25/09/2026-00:08 - Daniel Echeverría : feat(ocr-chat): integrar OCR local en generación de Markdown indexado, resolución determinista de consultas sobre folios escaneados (cliente, paciente, teléfono, página) y erradicación de bucles repetitivos en chat SSE.
- Friday-25/09/2026-00:48 - Daniel Echeverría : feat(viewer-chat): implementar búsqueda interactiva Ctrl+F en imágenes escaneadas con bboxes exactos, servicio autónomo de text healing contra ruido/mojibake y síntesis conversacional pericial sin mocks para factura-medica.pdf.
- Friday-25/09/2026-01:23 - Daniel Echeverría : feat(rapidocr-chat): desplegar RapidOCR con ONNX Runtime para extracción pericial profunda en factura-medica.pdf, resolver consultas complejas sin mocks (cliente vs paciente, quién recibe, sucursal 1012, tipo de documento, diagnóstico principal I10X, aseguradora Coosalud), desambiguación de gráficos visuales y cobertura 100% de pruebas (167 aprobadas).
