# 📄 Módulo de Auditoría Documental Inteligente (IDP)

Cuadro de mando en Streamlit que sube un PDF, lo valida contra un checklist de
reglas de negocio y devuelve un informe de incidencias, un reporte JSON
estructurado y el documento con la auditoría anexada.

**Demo en vivo:** _(pega aquí la URL una vez desplegada)_

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.38%2B-red)

---

## Qué hace

| Fase | Detalle |
|---|---|
| **Ingesta** | Lectura del PDF en memoria (PyMuPDF / pypdf): páginas, texto y metadatos. Sin persistencia en disco. |
| **Validación** | 6 reglas de negocio configurables: firmas, fechas, importes, estructura, identificadores fiscales y protección de datos. |
| **Salida** | KPIs de cumplimiento, tabla de incidencias con severidad y evidencia, JSON para integrar en ERP/CRM y PDF corregido. |

### Dos motores de análisis

- **Simulación (por defecto).** No requiere clave ni tiene coste. Es
  **determinista**: se siembra con el SHA-256 del fichero, así que el mismo PDF
  produce siempre el mismo informe. Pensado para demostrar el flujo completo.
- **IA real.** Análisis con la API de Anthropic (`claude-opus-5`). Adjunta el PDF
  nativo cuando cabe en los límites de la API, de modo que el modelo *ve* firmas
  y maquetación, y usa salida estructurada con JSON Schema estricto.

> El modo IA requiere que **cada visitante aporte su propia clave**. La demo
> desplegada no incluye ninguna clave: nadie puede consumir crédito ajeno.

---

## Ejecución local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
streamlit run app.py
```

Para el modo IA, define la clave antes de arrancar (o pégala en la barra lateral):

```bash
set ANTHROPIC_API_KEY=sk-ant-...   # Windows
export ANTHROPIC_API_KEY=sk-ant-... # Linux / macOS
```

### Documento de ejemplo

`ejemplo/contrato_demo.pdf` es un contrato con errores deliberados (importes que
no cuadran, fecha de fin anterior a la de inicio, campo sin rellenar, firma
ausente, IBAN corto, salto de paginación). Se puede cargar desde la barra
lateral sin subir nada. Para regenerarlo: `python generar_ejemplo.py`.

---

## Despliegue en Streamlit Community Cloud (gratuito)

1. Sube **el contenido de esta carpeta** a un repositorio público de GitHub.
   `.gitignore` ya excluye `.venv/`, `.env` y `secrets.toml`.
2. Entra en <https://share.streamlit.io> con la cuenta de GitHub.
3. **New app** → elige el repositorio, la rama y `app.py` como *Main file path*.
4. En *Advanced settings*, selecciona Python **3.11** o superior.
5. **Deploy**. La URL resultante tiene la forma
   `https://<nombre-de-la-app>.streamlit.app` y es la que se pone en el CV.

No añadas `ANTHROPIC_API_KEY` en *Secrets*: la demo funciona en modo Simulación
y así ninguna visita consume tu crédito.

### Alternativa: Hugging Face Spaces

Crear un Space con SDK **Streamlit**, subir estos ficheros y añadir al principio
del `README.md` del Space el bloque:

```yaml
---
title: Auditoria Documental IDP
sdk: streamlit
app_file: app.py
---
```

URL resultante: `https://huggingface.co/spaces/<usuario>/<space>`.

---

## Estructura

```
app.py                     Aplicación completa
generar_ejemplo.py         Genera el PDF de demostración
requirements.txt           Dependencias
ejemplo/contrato_demo.pdf  Documento de prueba
.streamlit/config.toml     Tema y límite de subida
```

---

💡 **¿Funciones avanzadas?** Procesamiento en lote, integración vía API con
CRM/ERP o reglas personalizadas. Contacto: **603 460 945**
