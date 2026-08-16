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
| **Validación** | 6 reglas de negocio configurables: firmas, fechas, importes, estructura, identificadores fiscales y protección de datos. Cada incidencia se ancla a su página y cita la evidencia. |
| **Salida** | KPIs de cumplimiento, tabla de incidencias con severidad y evidencia, JSON para integrar en ERP/CRM y PDF corregido. |
| **Lote** | Con más de un documento aparece el panel agregado: cumplimiento medio, ranking de documentos y en qué regla se concentran los fallos. |

> La demo admite **hasta 2 documentos** por ejecución: corre en un contenedor
> gratuito y, en modo IA, cada documento es una llamada a la API. El
> procesamiento en lote sin límite es parte de la versión completa.

### Dos motores de análisis

- **Reglas deterministas (por defecto).** No requiere clave ni tiene coste.
  Analiza el texto realmente extraído del PDF: cuadre aritmético de los
  importes, orden cronológico de las fechas, formato de NIF/CIF e IBAN,
  marcadores sin rellenar, continuidad de la paginación, firmas en blanco y
  vigencia de la cláusula de protección de datos. **Cada hallazgo cita la
  evidencia encontrada**, así que el informe se puede contrastar con el
  documento. Si una regla no encuentra los campos que necesita, lo declara *no
  evaluable* en lugar de inventar un hallazgo.
- **IA real.** Análisis con la API de Anthropic (`claude-opus-5`) para
  documentos de estructura libre. Adjunta el PDF nativo cuando cabe en los
  límites de la API, de modo que el modelo *ve* firmas y maquetación, y usa
  salida estructurada con JSON Schema estricto.

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

### Documentos de ejemplo — pruébalo y compruébalo

En la barra lateral hay dos facturas de **una sola página**, descargables, para
que cualquiera pueda revisarlas a simple vista y contrastar el informe:

| Documento | Qué debe salir |
|---|---|
| `ejemplo/ejemplo_conforme.pdf` | **0 incumplimientos**, 100 % de cumplimiento |
| `ejemplo/ejemplo_con_errores.pdf` | **7 incumplimientos**, uno por cada defecto |
| Las dos como lote | **50 %** de cumplimiento medio, 1 conforme de 2, 7 incidencias |

Los 7 defectos deliberados del segundo documento:

1. **Importes** — TOTAL 1.310,00 € cuando 1.000,00 + 210,00 = 1.210,00 €
2. **Fechas** — fin (15/02/2026) anterior al inicio (01/03/2026)
3. **Estructura** — Nº de factura sin rellenar: `[PENDIENTE]`
4. **Identificadores** — CIF del emisor: `(no consta)`
5. **Identificadores** — IBAN de 23 caracteres (los españoles tienen 24)
6. **Firmas** — la firma del receptor está en blanco
7. **Protección de datos** — cita la LOPD 15/1999, derogada en 2018

Para regenerar ambos PDFs: `python generar_ejemplos.py`.

---

## Registro de visitas (lead capture)

La demo está **cerrada tras un formulario**: sin identificarse no se accede a
la herramienta. Cada acceso se registra en una hoja de cálculo de Google con
fecha, nombre, empresa, email, cargo, motivo de la visita, consentimiento y
origen (`?origen=linkedin`, `?origen=cv`… para medir por dónde llegan).

### Antes de publicar

1. **Completa `RESPONSABLE_TRATAMIENTO` en `app.py`.** El art. 13 del RGPD
   obliga a identificar al responsable; mientras contenga el marcador, la app
   muestra un aviso en el propio formulario.
2. Revisa `EMAIL_CONTACTO_RGPD` y `CONSERVACION_DATOS`.

### Configurar Google Sheets

1. En <https://console.cloud.google.com> crea un proyecto.
2. *APIs y servicios* → habilita **Google Sheets API**.
3. *Credenciales* → *Crear credenciales* → **Cuenta de servicio**.
4. En la cuenta creada: *Claves* → *Añadir clave* → **JSON** (se descarga).
5. Crea la hoja de cálculo y **compártela con el `client_email`** de la cuenta
   de servicio, con permiso de **Editor**. Sin este paso, la escritura falla.
6. Copia el contenido de `.streamlit/secrets.toml.example`, rellénalo con los
   valores del JSON y pégalo en Streamlit Cloud → *Manage app* → *Settings* →
   *Secrets*. **Nunca subas ese fichero al repositorio.**

Sin credenciales configuradas la app no se rompe: guarda los leads en
`leads_local.csv`, que sirve ejecutando en local. **En Streamlit Cloud ese
fichero se pierde en cada redespliegue**, así que la hoja de cálculo no es
opcional si quieres conservar los registros.

Para saltarte la puerta mientras desarrollas: `DEMO_SIN_REGISTRO=1`.

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
app.py                            Aplicación completa
generar_ejemplos.py               Genera los dos PDFs de demostración
requirements.txt                  Dependencias
ejemplo/ejemplo_conforme.pdf      Factura correcta
ejemplo/ejemplo_con_errores.pdf   Factura con 7 defectos deliberados
.streamlit/config.toml            Tema y límite de subida
```

---

## Hoja de ruta (versión completa)

Lo que la demo deja fuera a propósito:

- **Lote sin límite** — colas de cientos de documentos con reanudación.
- **Conciliación cruzada** — contrastar documentos *entre sí* (que el importe
  de la factura coincida con el del contrato, que el CIF sea el mismo en todo
  el expediente). Requiere definir qué campos deben casar entre qué tipos de
  documento: es trabajo a medida de cada cliente.
- **Integración vía API** con el CRM/ERP y reglas de negocio propias.

---

💡 **¿Funciones avanzadas?** Procesamiento en lote sin límite, conciliación
entre documentos, integración vía API con CRM/ERP o reglas personalizadas.
Contacto: **603 460 945**
