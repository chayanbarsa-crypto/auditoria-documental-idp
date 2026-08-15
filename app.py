"""
Módulo de Auditoría Documental Inteligente (IDP)
================================================

Demo de portfolio: cuadro de mando en Streamlit que permite subir un PDF,
aplicar un checklist de reglas de negocio, ejecutar el análisis (simulado o
con IA real vía la API de Anthropic) y descargar los resultados.

Ejecución:
    streamlit run app.py

Dependencias mínimas:
    pip install streamlit pandas
Opcionales (la app degrada con elegancia si faltan):
    pip install pymupdf        -> extracción de texto y metadatos del PDF
    pip install pypdf          -> alternativa de extracción / fusión de PDFs
    pip install reportlab      -> generación del PDF corregido/anotado
    pip install anthropic      -> modo de análisis con IA real
    pip install python-dotenv  -> carga de la clave desde un fichero .env

Autor: Jordy — Demo comercial. Contacto: 603 460 945
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import random
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# 1. DEPENDENCIAS OPCIONALES
#    Se importan de forma defensiva: la demo debe arrancar aunque falte alguna.
# ---------------------------------------------------------------------------

try:  # Extractor preferido: rápido y con buenos metadatos.
    import pymupdf as fitz  # Nombre moderno del paquete (PyMuPDF >= 1.24).

    HAS_PYMUPDF = True
except ImportError:  # pragma: no cover - depende del entorno
    try:
        import fitz  # Alias histórico, aún válido en versiones antiguas.

        HAS_PYMUPDF = True
    except ImportError:
        HAS_PYMUPDF = False

try:
    from pypdf import PdfReader, PdfWriter

    HAS_PYPDF = True
except ImportError:  # pragma: no cover
    HAS_PYPDF = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover
    HAS_REPORTLAB = False

try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:  # pragma: no cover
    HAS_ANTHROPIC = False

try:  # Carga ANTHROPIC_API_KEY desde .env si existe.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# 2. CONFIGURACIÓN Y CATÁLOGO DE REGLAS DE NEGOCIO
# ---------------------------------------------------------------------------

APP_TITLE = "📄 Módulo de Auditoría Documental Inteligente (IDP)"
APP_SUBTITLE = (
    "Procesamiento, validación y corrección automatizada de PDFs "
    "contra reglas de negocio."
)
CONTACTO_TELEFONO = "603 460 945"

# Modelo por defecto para el modo IA real.
PDF_EJEMPLO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplo", "contrato_demo.pdf")

MODELO_IA = "claude-opus-5"
MAX_TOKENS_IA = 16_000
# Límites de la API para adjuntar el PDF nativo (visión sobre firmas, sellos...).
MAX_MB_PDF_NATIVO = 25
MAX_PAGINAS_PDF_NATIVO = 100

SEVERIDADES = ["Crítica", "Alta", "Media", "Baja", "Informativa"]
PESO_SEVERIDAD = {  # Penalización sobre el % de cumplimiento.
    "Crítica": 22,
    "Alta": 12,
    "Media": 6,
    "Baja": 2,
    "Informativa": 0,
}
COLOR_SEVERIDAD = {
    "Crítica": "#b3261e",
    "Alta": "#e8710a",
    "Media": "#c8a600",
    "Baja": "#4a7dbd",
    "Informativa": "#6c757d",
}


@dataclass(frozen=True)
class Regla:
    """Una regla del checklist de negocio."""

    id: str
    nombre: str
    descripcion: str
    # Instrucción que se inyecta en el prompt del modelo en el modo IA real.
    criterio_ia: str


CATALOGO_REGLAS: list[Regla] = [
    Regla(
        id="R01",
        nombre="Verificación de Firmas",
        descripcion="Presencia, ubicación y legibilidad de firmas y sellos.",
        criterio_ia=(
            "Comprueba que el documento está firmado: busca firmas manuscritas, "
            "firmas digitales, sellos y bloques 'Firmado por'. Señala firmas "
            "ausentes, ilegibles, sin identificación del firmante o sin fecha."
        ),
    ),
    Regla(
        id="R02",
        nombre="Cumplimiento de Fechas",
        descripcion="Coherencia cronológica y vigencia de las fechas.",
        criterio_ia=(
            "Verifica todas las fechas: formato homogéneo, coherencia cronológica "
            "(inicio anterior a fin), vigencia respecto a la fecha de emisión y "
            "ausencia de fechas futuras imposibles o campos de fecha vacíos."
        ),
    ),
    Regla(
        id="R03",
        nombre="Validación de Importes",
        descripcion="Cuadre aritmético, divisas e impuestos.",
        criterio_ia=(
            "Valida los importes: que base imponible + impuestos = total, que la "
            "divisa sea consistente, que los decimales y separadores sean "
            "correctos y que no haya importes negativos o ausentes injustificados."
        ),
    ),
    Regla(
        id="R04",
        nombre="Estructura de Datos",
        descripcion="Campos obligatorios, secciones y numeración.",
        criterio_ia=(
            "Revisa la estructura: presencia de los campos obligatorios "
            "(emisor, receptor, identificador del documento, objeto), numeración "
            "de páginas, secciones completas y ausencia de campos marcador sin "
            "rellenar del tipo 'XXXX' o '[pendiente]'."
        ),
    ),
    Regla(
        id="R05",
        nombre="Identificadores Fiscales",
        descripcion="Formato y presencia de NIF/CIF/IBAN.",
        criterio_ia=(
            "Comprueba los identificadores fiscales y bancarios: formato válido de "
            "NIF/CIF/NIE e IBAN, presencia de ambos cuando el documento lo exige y "
            "coherencia entre el identificador y el nombre de la entidad."
        ),
    ),
    Regla(
        id="R06",
        nombre="Protección de Datos (LOPD)",
        descripcion="Datos personales expuestos y cláusulas informativas.",
        criterio_ia=(
            "Detecta datos personales sensibles expuestos sin anonimizar y verifica "
            "la presencia de la cláusula informativa de protección de datos "
            "(RGPD/LOPDGDD) cuando el tipo de documento la requiere."
        ),
    ),
]

REGLAS_POR_NOMBRE = {r.nombre: r for r in CATALOGO_REGLAS}
REGLAS_POR_DEFECTO = [
    "Verificación de Firmas",
    "Cumplimiento de Fechas",
    "Validación de Importes",
    "Estructura de Datos",
]


# ---------------------------------------------------------------------------
# 3. MODELO DE DATOS DEL RESULTADO
# ---------------------------------------------------------------------------


@dataclass
class Hallazgo:
    """Una incidencia detectada por el motor de auditoría."""

    regla: str
    pagina: int
    severidad: str
    estado: str  # Cumple | No cumple | Requiere revisión
    descripcion: str
    evidencia: str = ""
    sugerencia: str = ""


@dataclass
class ResultadoAuditoria:
    """Salida completa de una auditoría, serializable a JSON."""

    documento: str
    motor: str
    modelo: str | None
    fecha_utc: str
    paginas: int
    tamano_kb: float
    reglas_aplicadas: list[str]
    cumplimiento: int
    resumen: str
    hallazgos: list[Hallazgo] = field(default_factory=list)
    metadatos: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["hallazgos"] = [asdict(h) for h in self.hallazgos]
        return datos

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 4. LECTURA DEL PDF
# ---------------------------------------------------------------------------


def leer_pdf(datos: bytes) -> tuple[int, str, dict[str, Any]]:
    """Devuelve (nº de páginas, texto extraído, metadatos) de un PDF en memoria.

    Prueba PyMuPDF y, si no está disponible, pypdf. Si ninguno está instalado
    devuelve valores neutros para que la demo siga siendo utilizable.
    """
    if HAS_PYMUPDF:
        with fitz.open(stream=datos, filetype="pdf") as doc:
            paginas = doc.page_count
            texto = "\n".join(pagina.get_text() for pagina in doc)
            meta = {k: v for k, v in (doc.metadata or {}).items() if v}
        return paginas, texto, meta

    if HAS_PYPDF:
        lector = PdfReader(io.BytesIO(datos))
        paginas = len(lector.pages)
        texto = "\n".join((p.extract_text() or "") for p in lector.pages)
        meta = {
            k.lstrip("/"): str(v)
            for k, v in (lector.metadata or {}).items()
            if v
        }
        return paginas, texto, meta

    # Sin librería de PDF: estimación grosera del nº de páginas por marcadores.
    paginas = max(1, datos.count(b"/Type /Page") or datos.count(b"/Type/Page"))
    return paginas, "", {"aviso": "Instala pymupdf o pypdf para extraer texto."}


def es_pdf(datos: bytes) -> bool:
    """Comprueba la cabecera mágica del fichero."""
    return datos[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# 5. MOTOR A — SIMULACIÓN (sin coste, determinista por documento)
# ---------------------------------------------------------------------------

# Plantillas de hallazgo por regla: (severidad, descripción, evidencia, sugerencia)
PLANTILLAS_SIMULACION: dict[str, list[tuple[str, str, str, str]]] = {
    "R01": [
        (
            "Crítica",
            "Falta la firma del representante legal en el bloque de cierre.",
            "Recuadro 'Firma del representante' vacío.",
            "Recabar firma manuscrita o electrónica cualificada antes de archivar.",
        ),
        (
            "Media",
            "Firma presente pero sin identificación legible del firmante.",
            "Rúbrica sin nombre ni DNI asociado.",
            "Añadir nombre completo y NIF bajo la rúbrica.",
        ),
        (
            "Baja",
            "El sello corporativo se solapa con el texto del párrafo final.",
            "Sello desplazado sobre la línea de importe.",
            "Reubicar el sello en el margen inferior derecho.",
        ),
    ],
    "R02": [
        (
            "Alta",
            "La fecha de fin de vigencia es anterior a la fecha de inicio.",
            "Inicio 01/09/2025 — Fin 15/08/2025.",
            "Corregir la fecha de fin o justificar la prórroga retroactiva.",
        ),
        (
            "Media",
            "Convivencia de dos formatos de fecha en el mismo documento.",
            "Se detecta DD/MM/AAAA y AAAA-MM-DD.",
            "Homogeneizar a DD/MM/AAAA en todo el documento.",
        ),
        (
            "Informativa",
            "El documento supera los 12 meses desde su emisión.",
            "Fecha de emisión fuera del ejercicio corriente.",
            "Verificar si procede una revisión anual del expediente.",
        ),
    ],
    "R03": [
        (
            "Crítica",
            "El total no cuadra con la suma de base imponible e impuestos.",
            "Base 1.240,00 € + IVA 260,40 € ≠ Total 1.520,40 €.",
            "Recalcular el total: el importe correcto es 1.500,40 €.",
        ),
        (
            "Alta",
            "Se aplica un tipo impositivo distinto al esperado para el concepto.",
            "IVA al 10 % sobre un servicio de consultoría.",
            "Revisar el tipo aplicable (21 %) y reemitir si procede.",
        ),
        (
            "Baja",
            "Uso inconsistente del separador de miles y decimales.",
            "Coexisten 1,240.00 y 1.240,00.",
            "Unificar al formato español: 1.240,00 €.",
        ),
    ],
    "R04": [
        (
            "Alta",
            "Campo obligatorio sin rellenar en la cabecera del documento.",
            "Marcador '[PENDIENTE]' en el campo 'Nº de expediente'.",
            "Completar el identificador antes de la firma.",
        ),
        (
            "Media",
            "La numeración de páginas no es continua.",
            "Salto detectado entre 'Pág. 3' y 'Pág. 5'.",
            "Regenerar el documento con paginación continua.",
        ),
        (
            "Baja",
            "Falta el anexo referenciado en el cuerpo del texto.",
            "Se cita 'Anexo II' pero el documento no lo incluye.",
            "Adjuntar el Anexo II o eliminar la referencia.",
        ),
    ],
    "R05": [
        (
            "Crítica",
            "El dígito de control del CIF no valida.",
            "CIF declarado con checksum incorrecto.",
            "Verificar el identificador contra el censo y corregirlo.",
        ),
        (
            "Alta",
            "IBAN con longitud incorrecta para el país indicado.",
            "IBAN español con 22 caracteres en lugar de 24.",
            "Solicitar de nuevo el certificado de titularidad bancaria.",
        ),
        (
            "Media",
            "No consta el NIF del receptor del documento.",
            "Bloque 'Datos del destinatario' incompleto.",
            "Completar el NIF del destinatario.",
        ),
    ],
    "R06": [
        (
            "Crítica",
            "Datos personales sin anonimizar en un documento de circulación externa.",
            "DNI y domicilio completos visibles en el cuerpo.",
            "Aplicar seudonimización o redacción parcial antes de distribuir.",
        ),
        (
            "Alta",
            "Falta la cláusula informativa de protección de datos.",
            "No se localiza mención al RGPD ni al responsable del tratamiento.",
            "Incorporar la cláusula informativa estándar al pie.",
        ),
        (
            "Baja",
            "La cláusula de protección de datos está desactualizada.",
            "Se cita la LOPD de 1999 en lugar de la LOPDGDD 3/2018.",
            "Actualizar la referencia normativa.",
        ),
    ],
}


def auditar_simulado(
    datos: bytes,
    nombre: str,
    paginas: int,
    texto: str,
    metadatos: dict[str, Any],
    reglas: list[Regla],
) -> ResultadoAuditoria:
    """Genera un resultado verosímil y **determinista** para el documento dado.

    El generador se siembra con el hash del fichero, de modo que el mismo PDF
    con el mismo checklist produce siempre el mismo informe: imprescindible
    para que una demo comercial sea reproducible delante del cliente.
    """
    semilla = int(hashlib.sha256(datos).hexdigest()[:16], 16)
    rnd = random.Random(semilla)

    hallazgos: list[Hallazgo] = []
    for regla in reglas:
        plantillas = PLANTILLAS_SIMULACION.get(regla.id, [])
        if not plantillas:
            continue
        # Entre 0 y 2 incidencias por regla: no todo documento falla en todo.
        n = rnd.choices([0, 1, 2], weights=[35, 45, 20])[0]
        for severidad, descripcion, evidencia, sugerencia in rnd.sample(
            plantillas, k=min(n, len(plantillas))
        ):
            hallazgos.append(
                Hallazgo(
                    regla=regla.nombre,
                    pagina=rnd.randint(1, max(1, paginas)),
                    severidad=severidad,
                    estado="No cumple"
                    if severidad in ("Crítica", "Alta")
                    else "Requiere revisión",
                    descripcion=descripcion,
                    evidencia=evidencia,
                    sugerencia=sugerencia,
                )
            )

    # Reglas sin incidencias -> se registran explícitamente como conformes.
    reglas_con_fallo = {h.regla for h in hallazgos}
    for regla in reglas:
        if regla.nombre not in reglas_con_fallo:
            hallazgos.append(
                Hallazgo(
                    regla=regla.nombre,
                    pagina=0,
                    severidad="Informativa",
                    estado="Cumple",
                    descripcion=f"Sin incidencias detectadas para «{regla.nombre}».",
                    evidencia="Validación superada en todas las páginas revisadas.",
                    sugerencia="",
                )
            )

    hallazgos.sort(key=lambda h: (SEVERIDADES.index(h.severidad), h.pagina))
    cumplimiento = calcular_cumplimiento(hallazgos)
    criticos = sum(1 for h in hallazgos if h.severidad == "Crítica")

    resumen = (
        f"Se han revisado {paginas} página(s) contra {len(reglas)} regla(s) de negocio. "
        f"El documento alcanza un {cumplimiento} % de cumplimiento con "
        f"{len([h for h in hallazgos if h.estado != 'Cumple'])} incidencia(s) abierta(s), "
        f"de las cuales {criticos} son de severidad crítica. "
        + (
            "Se recomienda subsanar las incidencias críticas antes de dar el "
            "documento por válido."
            if criticos
            else "No se detectan bloqueantes: el documento puede continuar el flujo."
        )
    )

    return ResultadoAuditoria(
        documento=nombre,
        motor="Simulación determinista",
        modelo=None,
        fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        paginas=paginas,
        tamano_kb=round(len(datos) / 1024, 1),
        reglas_aplicadas=[r.nombre for r in reglas],
        cumplimiento=cumplimiento,
        resumen=resumen,
        hallazgos=hallazgos,
        metadatos=metadatos,
    )


def calcular_cumplimiento(hallazgos: list[Hallazgo]) -> int:
    """Puntúa de 0 a 100 penalizando cada incidencia según su severidad."""
    penalizacion = sum(
        PESO_SEVERIDAD.get(h.severidad, 0) for h in hallazgos if h.estado != "Cumple"
    )
    return max(0, min(100, 100 - penalizacion))


# ---------------------------------------------------------------------------
# 6. MOTOR B — IA REAL (API de Anthropic)
# ---------------------------------------------------------------------------

# Esquema JSON estricto: garantiza que la respuesta del modelo es parseable.
ESQUEMA_SALIDA = {
    "type": "object",
    "properties": {
        "cumplimiento": {
            "type": "integer",
            "description": "Porcentaje global de cumplimiento, de 0 a 100.",
        },
        "resumen": {
            "type": "string",
            "description": "Resumen ejecutivo de la auditoría, 3-5 frases.",
        },
        "hallazgos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "regla": {"type": "string"},
                    "pagina": {"type": "integer"},
                    "severidad": {"type": "string", "enum": SEVERIDADES},
                    "estado": {
                        "type": "string",
                        "enum": ["Cumple", "No cumple", "Requiere revisión"],
                    },
                    "descripcion": {"type": "string"},
                    "evidencia": {"type": "string"},
                    "sugerencia": {"type": "string"},
                },
                "required": [
                    "regla",
                    "pagina",
                    "severidad",
                    "estado",
                    "descripcion",
                    "evidencia",
                    "sugerencia",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cumplimiento", "resumen", "hallazgos"],
    "additionalProperties": False,
}

PROMPT_SISTEMA = (
    "Eres un auditor documental senior especializado en Intelligent Document "
    "Processing. Analizas documentos PDF contra un checklist de reglas de "
    "negocio y devuelves hallazgos accionables.\n\n"
    "Criterios de trabajo:\n"
    "- Un hallazgo por incidencia concreta, anclado a la página donde aparece.\n"
    "- Si una regla se cumple sin incidencias, emite un hallazgo con "
    "estado 'Cumple' y severidad 'Informativa'.\n"
    "- La evidencia debe citar lo que se ve en el documento, no inferencias.\n"
    "- No inventes datos: si un campo no es legible, márcalo como "
    "'Requiere revisión' en lugar de asumir su contenido.\n"
    "- La sugerencia debe ser una acción concreta de subsanación."
)


def construir_prompt_usuario(reglas: list[Regla], texto: str, adjunto: bool) -> str:
    """Compone la instrucción con el checklist seleccionado."""
    checklist = "\n".join(
        f"- [{r.id}] {r.nombre}: {r.criterio_ia}" for r in reglas
    )
    partes = [
        "Audita el documento adjunto contra el siguiente checklist de reglas "
        "de negocio:\n",
        checklist,
        "\nDevuelve el resultado siguiendo estrictamente el esquema JSON "
        "solicitado. El campo 'cumplimiento' es tu valoración global de 0 a 100.",
    ]
    if not adjunto:
        partes.append(
            "\n--- TEXTO EXTRAÍDO DEL DOCUMENTO ---\n" + texto[:120_000]
        )
    return "\n".join(partes)


def auditar_con_ia(
    datos: bytes,
    nombre: str,
    paginas: int,
    texto: str,
    metadatos: dict[str, Any],
    reglas: list[Regla],
    api_key: str,
) -> ResultadoAuditoria:
    """Ejecuta la auditoría real contra la API de Anthropic.

    Adjunta el PDF nativo cuando cabe dentro de los límites de la API (así el
    modelo "ve" firmas, sellos y maquetación); en caso contrario envía el texto
    extraído como plan B.
    """
    if not HAS_ANTHROPIC:
        raise RuntimeError(
            "El paquete 'anthropic' no está instalado. Ejecuta: pip install anthropic"
        )

    cliente = anthropic.Anthropic(api_key=api_key)

    # ¿Cabe el PDF nativo? Da mucha mejor precisión en firmas y maquetación.
    cabe_nativo = (
        len(datos) <= MAX_MB_PDF_NATIVO * 1024 * 1024
        and paginas <= MAX_PAGINAS_PDF_NATIVO
    )

    contenido: list[dict[str, Any]] = []
    if cabe_nativo:
        contenido.append(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(datos).decode("ascii"),
                },
            }
        )
    contenido.append(
        {
            "type": "text",
            "text": construir_prompt_usuario(reglas, texto, adjunto=cabe_nativo),
        }
    )

    respuesta = cliente.messages.create(
        model=MODELO_IA,
        max_tokens=MAX_TOKENS_IA,
        system=PROMPT_SISTEMA,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": ESQUEMA_SALIDA},
        },
        messages=[{"role": "user", "content": contenido}],
    )

    if respuesta.stop_reason == "refusal":
        raise RuntimeError(
            "El modelo ha declinado analizar este documento. "
            "Revisa su contenido o prueba con otro fichero."
        )

    bruto = next(
        (b.text for b in respuesta.content if getattr(b, "type", "") == "text"), ""
    )
    if not bruto:
        raise RuntimeError("La API no ha devuelto contenido analizable.")

    datos_json = json.loads(bruto)
    hallazgos = [
        Hallazgo(
            regla=str(h.get("regla", "—")),
            pagina=int(h.get("pagina", 0) or 0),
            severidad=h.get("severidad", "Informativa"),
            estado=h.get("estado", "Requiere revisión"),
            descripcion=h.get("descripcion", ""),
            evidencia=h.get("evidencia", ""),
            sugerencia=h.get("sugerencia", ""),
        )
        for h in datos_json.get("hallazgos", [])
    ]
    hallazgos.sort(
        key=lambda h: (
            SEVERIDADES.index(h.severidad) if h.severidad in SEVERIDADES else 99,
            h.pagina,
        )
    )

    uso = respuesta.usage
    metadatos_ampliados = dict(metadatos)
    metadatos_ampliados["tokens_entrada"] = getattr(uso, "input_tokens", None)
    metadatos_ampliados["tokens_salida"] = getattr(uso, "output_tokens", None)
    metadatos_ampliados["pdf_adjunto_nativo"] = cabe_nativo

    return ResultadoAuditoria(
        documento=nombre,
        motor="IA — API de Anthropic",
        modelo=MODELO_IA,
        fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        paginas=paginas,
        tamano_kb=round(len(datos) / 1024, 1),
        reglas_aplicadas=[r.nombre for r in reglas],
        cumplimiento=int(datos_json.get("cumplimiento", calcular_cumplimiento(hallazgos))),
        resumen=str(datos_json.get("resumen", "")),
        hallazgos=hallazgos,
        metadatos=metadatos_ampliados,
    )


# ---------------------------------------------------------------------------
# 7. GENERACIÓN DE ENTREGABLES
# ---------------------------------------------------------------------------


def construir_informe_markdown(res: ResultadoAuditoria) -> str:
    """Informe legible en Markdown (plan B si no hay reportlab)."""
    lineas = [
        f"# Informe de auditoría documental — {res.documento}",
        "",
        f"- **Fecha (UTC):** {res.fecha_utc}",
        f"- **Motor:** {res.motor}" + (f" ({res.modelo})" if res.modelo else ""),
        f"- **Páginas:** {res.paginas}  |  **Tamaño:** {res.tamano_kb} KB",
        f"- **Cumplimiento global:** {res.cumplimiento} %",
        f"- **Reglas aplicadas:** {', '.join(res.reglas_aplicadas)}",
        "",
        "## Resumen ejecutivo",
        "",
        res.resumen,
        "",
        "## Incidencias detectadas",
        "",
    ]
    abiertas = [h for h in res.hallazgos if h.estado != "Cumple"]
    if not abiertas:
        lineas.append("_Sin incidencias abiertas._")
    for i, h in enumerate(abiertas, start=1):
        lineas += [
            f"### {i}. [{h.severidad}] {h.regla} — página {h.pagina or 'n/d'}",
            "",
            f"- **Estado:** {h.estado}",
            f"- **Descripción:** {h.descripcion}",
            f"- **Evidencia:** {h.evidencia or '—'}",
            f"- **Corrección propuesta:** {h.sugerencia or '—'}",
            "",
        ]
    lineas += [
        "---",
        "",
        f"Generado por el Módulo de Auditoría Documental Inteligente (IDP). "
        f"Contacto: {CONTACTO_TELEFONO}",
    ]
    return "\n".join(lineas)


def construir_pdf_informe(res: ResultadoAuditoria) -> bytes | None:
    """Genera con reportlab el PDF del informe de auditoría."""
    if not HAS_REPORTLAB:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Auditoría IDP — {res.documento}",
    )
    estilos = getSampleStyleSheet()
    h1 = ParagraphStyle("h1x", parent=estilos["Heading1"], fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2x", parent=estilos["Heading2"], fontSize=12, spaceAfter=6)
    normal = ParagraphStyle("nx", parent=estilos["BodyText"], fontSize=9, leading=13)
    pie = ParagraphStyle(
        "pie", parent=estilos["BodyText"], fontSize=8, textColor=colors.grey
    )

    elementos: list[Any] = [
        Paragraph("Informe de Auditoría Documental Inteligente (IDP)", h1),
        Paragraph(f"<b>Documento:</b> {res.documento}", normal),
        Paragraph(f"<b>Fecha (UTC):</b> {res.fecha_utc}", normal),
        Paragraph(
            f"<b>Motor:</b> {res.motor}" + (f" — {res.modelo}" if res.modelo else ""),
            normal,
        ),
        Paragraph(
            f"<b>Páginas:</b> {res.paginas} &nbsp;&nbsp; "
            f"<b>Tamaño:</b> {res.tamano_kb} KB &nbsp;&nbsp; "
            f"<b>Cumplimiento:</b> {res.cumplimiento} %",
            normal,
        ),
        Paragraph(f"<b>Reglas aplicadas:</b> {', '.join(res.reglas_aplicadas)}", normal),
        Spacer(1, 8),
        Paragraph("Resumen ejecutivo", h2),
        Paragraph(res.resumen, normal),
        Spacer(1, 10),
        Paragraph("Detalle de incidencias", h2),
    ]

    filas = [["#", "Severidad", "Regla", "Pág.", "Descripción y corrección propuesta"]]
    abiertas = [h for h in res.hallazgos if h.estado != "Cumple"]
    for i, h in enumerate(abiertas, start=1):
        detalle = h.descripcion
        if h.sugerencia:
            detalle += f"<br/><i>Corrección: {h.sugerencia}</i>"
        filas.append(
            [
                str(i),
                h.severidad,
                Paragraph(h.regla, normal),
                str(h.pagina or "—"),
                Paragraph(detalle, normal),
            ]
        )
    if len(filas) == 1:
        filas.append(["—", "—", "—", "—", Paragraph("Sin incidencias abiertas.", normal)])

    tabla = Table(filas, colWidths=[10 * mm, 22 * mm, 34 * mm, 12 * mm, 96 * mm])
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elementos += [
        tabla,
        Spacer(1, 12),
        Paragraph(
            "Informe generado automáticamente por el Módulo de Auditoría "
            f"Documental Inteligente (IDP). Contacto: {CONTACTO_TELEFONO}",
            pie,
        ),
    ]

    doc.build(elementos)
    return buffer.getvalue()


def construir_pdf_corregido(datos_originales: bytes, res: ResultadoAuditoria) -> bytes | None:
    """Devuelve el PDF original con el informe de auditoría anexado al final.

    Requiere reportlab (para el informe) y pypdf (para la fusión). Si falta
    pypdf se devuelve únicamente el informe en PDF.
    """
    informe = construir_pdf_informe(res)
    if informe is None:
        return None
    if not HAS_PYPDF:
        return informe

    try:
        escritor = PdfWriter()
        for pagina in PdfReader(io.BytesIO(datos_originales)).pages:
            escritor.add_page(pagina)
        for pagina in PdfReader(io.BytesIO(informe)).pages:
            escritor.add_page(pagina)
        escritor.add_metadata(
            {
                "/Title": f"Auditoría IDP — {res.documento}",
                "/Subject": f"Cumplimiento {res.cumplimiento} %",
                "/Producer": "Módulo de Auditoría Documental Inteligente (IDP)",
            }
        )
        salida = io.BytesIO()
        escritor.write(salida)
        return salida.getvalue()
    except Exception:  # PDF cifrado o corrupto: al menos entregamos el informe.
        return informe


def nombre_base(nombre_fichero: str) -> str:
    """Nombre de fichero saneado para los descargables."""
    base = re.sub(r"\.pdf$", "", nombre_fichero, flags=re.IGNORECASE)
    return re.sub(r"[^\w\-]+", "_", base)[:60] or "documento"


# ---------------------------------------------------------------------------
# 8. INTERFAZ — BARRA LATERAL
# ---------------------------------------------------------------------------


def render_sidebar() -> dict[str, Any]:
    """Dibuja la barra lateral y devuelve la configuración elegida."""
    with st.sidebar:
        st.header("⚙️ Configuración de la auditoría")

        st.subheader("1. Checklist de reglas")
        nombres = st.multiselect(
            "Reglas de negocio a aplicar",
            options=list(REGLAS_POR_NOMBRE.keys()),
            default=REGLAS_POR_DEFECTO,
            help="Cada regla se traduce en un criterio de validación sobre el PDF.",
        )
        with st.expander("Ver descripción de las reglas"):
            for regla in CATALOGO_REGLAS:
                st.markdown(f"**{regla.nombre}** — {regla.descripcion}")

        st.subheader("2. Documento")
        fichero = st.file_uploader(
            "Sube el PDF a auditar",
            type=["pdf"],
            help="El fichero se procesa en memoria; no se almacena en disco.",
        )

        # Documento de ejemplo: permite probar la demo sin traer un fichero
        # propio. Incluye errores deliberados para que la auditoría tenga algo
        # real que detectar.
        usar_ejemplo = False
        if os.path.exists(PDF_EJEMPLO):
            usar_ejemplo = st.checkbox(
                "📄 Usar documento de ejemplo",
                value=False,
                disabled=fichero is not None,
                help="Contrato de prueba con errores deliberados de importes, "
                "fechas, firmas y estructura.",
            )
            if fichero is not None and usar_ejemplo:
                usar_ejemplo = False

        st.subheader("3. Motor de análisis")
        motor = st.radio(
            "Modo de ejecución",
            options=["Simulación (demo)", "IA real (API Anthropic)"],
            captions=[
                "Resultados deterministas, sin coste ni clave.",
                f"Análisis real del documento con {MODELO_IA}.",
            ],
            index=0,
        )

        api_key = ""
        if motor.startswith("IA real"):
            if not HAS_ANTHROPIC:
                st.warning("Instala el SDK: `pip install anthropic`")
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                st.success("Clave detectada en el entorno (ANTHROPIC_API_KEY).")
            else:
                api_key = st.text_input(
                    "ANTHROPIC_API_KEY",
                    type="password",
                    help="No se guarda: vive solo en la sesión del navegador.",
                )

        hay_documento = fichero is not None or usar_ejemplo

        st.divider()
        lanzar = st.button(
            "🚀 Ejecutar auditoría",
            type="primary",
            width="stretch",
            disabled=not hay_documento or not nombres,
        )
        if not hay_documento:
            st.caption("Sube un PDF o marca el documento de ejemplo.")
        elif not nombres:
            st.caption("Selecciona al menos una regla del checklist.")

        st.divider()
        st.caption("Demo de portfolio · Procesamiento inteligente de documentos")

    return {
        "reglas": [REGLAS_POR_NOMBRE[n] for n in nombres],
        "fichero": fichero,
        "usar_ejemplo": usar_ejemplo,
        "motor": motor,
        "api_key": api_key,
        "lanzar": lanzar,
    }


def obtener_documento(config: dict[str, Any]) -> tuple[str, bytes] | None:
    """Devuelve (nombre, bytes) del PDF a auditar: el subido o el de ejemplo."""
    fichero = config["fichero"]
    if fichero is not None:
        return fichero.name, fichero.getvalue()
    if config.get("usar_ejemplo") and os.path.exists(PDF_EJEMPLO):
        with open(PDF_EJEMPLO, "rb") as fh:
            return "contrato_demo.pdf", fh.read()
    return None


# ---------------------------------------------------------------------------
# 9. INTERFAZ — PANEL DE RESULTADOS
# ---------------------------------------------------------------------------


def render_metricas(res: ResultadoAuditoria) -> None:
    """Fila de KPIs del cuadro de mando."""
    abiertas = [h for h in res.hallazgos if h.estado != "Cumple"]
    criticas = [h for h in abiertas if h.severidad in ("Crítica", "Alta")]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Páginas procesadas", res.paginas)
    c2.metric(
        "Estado de cumplimiento",
        f"{res.cumplimiento} %",
        delta=f"{res.cumplimiento - 100} pts vs. óptimo" if res.cumplimiento < 100 else "Conforme",
        delta_color="inverse" if res.cumplimiento < 100 else "normal",
    )
    c3.metric("Errores detectados", len(abiertas))
    c4.metric("Críticos / Altos", len(criticas))

    st.progress(
        res.cumplimiento / 100,
        text=f"Nivel de conformidad documental: {res.cumplimiento} %",
    )


def render_incidencias(res: ResultadoAuditoria) -> None:
    """Tabla interactiva de incidencias con filtros."""
    if not res.hallazgos:
        st.info("El motor no ha devuelto hallazgos para este documento.")
        return

    df = pd.DataFrame([asdict(h) for h in res.hallazgos])
    df = df.rename(
        columns={
            "regla": "Regla",
            "pagina": "Página",
            "severidad": "Severidad",
            "estado": "Estado",
            "descripcion": "Descripción",
            "evidencia": "Evidencia",
            "sugerencia": "Corrección propuesta",
        }
    )

    col_f1, col_f2 = st.columns(2)
    sev = col_f1.multiselect(
        "Filtrar por severidad",
        options=[s for s in SEVERIDADES if s in set(df["Severidad"])],
        default=[s for s in SEVERIDADES if s in set(df["Severidad"])],
    )
    estados = col_f2.multiselect(
        "Filtrar por estado",
        options=sorted(df["Estado"].unique()),
        default=sorted(df["Estado"].unique()),
    )
    vista = df[df["Severidad"].isin(sev) & df["Estado"].isin(estados)]

    st.dataframe(
        vista,
        width="stretch",
        hide_index=True,
        column_config={
            "Página": st.column_config.NumberColumn(width="small", format="%d"),
            "Severidad": st.column_config.TextColumn(width="small"),
            "Estado": st.column_config.TextColumn(width="small"),
            "Descripción": st.column_config.TextColumn(width="large"),
        },
    )

    # Distribución por severidad: lectura rápida del riesgo del expediente.
    conteo = (
        df[df["Estado"] != "Cumple"]["Severidad"]
        .value_counts()
        .reindex(SEVERIDADES)
        .fillna(0)
        .astype(int)
    )
    if conteo.sum():
        st.markdown("**Distribución de incidencias por severidad**")
        st.bar_chart(conteo, height=220)


def render_detalle(res: ResultadoAuditoria) -> None:
    """Vista previa narrada de la auditoría, incidencia a incidencia."""
    abiertas = [h for h in res.hallazgos if h.estado != "Cumple"]
    if not abiertas:
        st.success("✅ El documento supera todas las reglas del checklist aplicado.")
        return

    for h in abiertas:
        color = COLOR_SEVERIDAD.get(h.severidad, "#6c757d")
        with st.expander(
            f"[{h.severidad}] {h.regla} — página {h.pagina or 'n/d'}", expanded=False
        ):
            st.markdown(
                f"<span style='background:{color};color:#fff;padding:2px 8px;"
                f"border-radius:10px;font-size:0.8rem'>{h.estado}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Descripción.** {h.descripcion}")
            if h.evidencia:
                st.markdown(f"**Evidencia.** _{h.evidencia}_")
            if h.sugerencia:
                st.markdown(f"**Corrección propuesta.** {h.sugerencia}")


def render_descargas(res: ResultadoAuditoria, datos_pdf: bytes) -> None:
    """Bloque de entregables: JSON estructurado + documento corregido."""
    base = nombre_base(res.documento)

    c1, c2, c3 = st.columns(3)

    c1.download_button(
        "⬇️ Reporte estructurado (JSON)",
        data=res.to_json().encode("utf-8"),
        file_name=f"auditoria_{base}.json",
        mime="application/json",
        width="stretch",
    )

    pdf_corregido = construir_pdf_corregido(datos_pdf, res)
    if pdf_corregido:
        c2.download_button(
            "⬇️ Documento corregido (PDF)",
            data=pdf_corregido,
            file_name=f"corregido_{base}.pdf",
            mime="application/pdf",
            width="stretch",
        )
    else:
        c2.button(
            "⬇️ Documento corregido (PDF)",
            disabled=True,
            width="stretch",
            help="Requiere reportlab: pip install reportlab",
        )

    c3.download_button(
        "⬇️ Informe legible (Markdown)",
        data=construir_informe_markdown(res).encode("utf-8"),
        file_name=f"informe_{base}.md",
        mime="text/markdown",
        width="stretch",
    )

    with st.expander("Vista previa del JSON estructurado"):
        st.json(res.to_dict())


def render_banner_comercial() -> None:
    """Pie de página / banner comercial de la demo."""
    st.divider()
    st.markdown(
        f"""
<div style="
    background: linear-gradient(90deg, #0f172a 0%, #1e3a8a 100%);
    color: #ffffff;
    padding: 22px 26px;
    border-radius: 14px;
    line-height: 1.6;
">
  <div style="font-size:1.12rem; font-weight:700; margin-bottom:6px;">
    💡 ¿Quieres ver funciones avanzadas?
  </div>
  <div style="font-size:0.97rem; opacity:0.93;">
    Procesamiento en lote, integración vía API con CRM/ERP o reglas personalizadas.
  </div>
  <div style="font-size:1.05rem; font-weight:700; margin-top:12px;">
    📞 Contacta directamente con el desarrollador:
    <span style="letter-spacing:0.5px;">{CONTACTO_TELEFONO}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 10. APLICACIÓN
# ---------------------------------------------------------------------------


def ejecutar_auditoria(config: dict[str, Any]) -> None:
    """Orquesta lectura, análisis y almacenamiento del resultado en sesión."""
    documento = obtener_documento(config)
    if documento is None:
        st.error("No hay ningún documento seleccionado.")
        return
    nombre_documento, datos = documento

    if not es_pdf(datos):
        st.error("El fichero subido no es un PDF válido (cabecera incorrecta).")
        return

    with st.status("Procesando documento…", expanded=True) as estado:
        st.write("📖 Extrayendo texto, páginas y metadatos…")
        try:
            paginas, texto, metadatos = leer_pdf(datos)
        except Exception as exc:
            estado.update(label="Error al leer el PDF", state="error")
            st.error(f"No se ha podido leer el documento: {exc}")
            return

        if not HAS_PYMUPDF and not HAS_PYPDF:
            st.warning(
                "Sin `pymupdf` ni `pypdf` instalados: la extracción de texto es "
                "limitada. Instala uno de los dos para un análisis completo."
            )

        st.write(f"🔎 Aplicando {len(config['reglas'])} regla(s) sobre {paginas} página(s)…")
        try:
            if config["motor"].startswith("IA real"):
                if not config["api_key"]:
                    estado.update(label="Falta la clave de API", state="error")
                    st.error(
                        "Introduce tu ANTHROPIC_API_KEY en la barra lateral o "
                        "defínela como variable de entorno."
                    )
                    return
                st.write(f"🤖 Consultando al modelo {MODELO_IA}…")
                resultado = auditar_con_ia(
                    datos, nombre_documento, paginas, texto, metadatos,
                    config["reglas"], config["api_key"],
                )
            else:
                resultado = auditar_simulado(
                    datos, nombre_documento, paginas, texto, metadatos, config["reglas"]
                )
        except Exception as exc:
            estado.update(label="Error durante el análisis", state="error")
            st.error(f"La auditoría no ha podido completarse: {exc}")
            return

        st.write("🧾 Consolidando hallazgos y entregables…")
        estado.update(label="Auditoría completada", state="complete", expanded=False)

    st.session_state["resultado"] = resultado
    st.session_state["pdf_bytes"] = datos


def main() -> None:
    st.set_page_config(
        page_title="Auditoría Documental Inteligente (IDP)",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    config = render_sidebar()

    if config["lanzar"]:
        ejecutar_auditoria(config)

    resultado: ResultadoAuditoria | None = st.session_state.get("resultado")
    datos_pdf: bytes | None = st.session_state.get("pdf_bytes")

    if resultado is None or datos_pdf is None:
        # Estado inicial: explica la propuesta de valor antes del primer análisis.
        st.info(
            "👈 Sube un PDF —o marca **Usar documento de ejemplo**—, elige el "
            "checklist de reglas y pulsa **Ejecutar auditoría** para generar "
            "el cuadro de mando. No hace falta clave de API: el modo "
            "*Simulación* funciona sin coste."
        )
        c1, c2, c3 = st.columns(3)
        c1.markdown(
            "#### 1. Ingesta\n"
            "Lectura del PDF en memoria: páginas, texto y metadatos. "
            "Sin persistencia en disco."
        )
        c2.markdown(
            "#### 2. Validación\n"
            "Cada regla de negocio se contrasta contra el documento y genera "
            "hallazgos anclados a página, con severidad y evidencia."
        )
        c3.markdown(
            "#### 3. Entregables\n"
            "Reporte estructurado en JSON para integrar en tu ERP/CRM y "
            "documento corregido con el informe anexado."
        )
        render_banner_comercial()
        return

    st.subheader(f"Resultados — `{resultado.documento}`")
    st.caption(
        f"Motor: **{resultado.motor}**"
        + (f" · Modelo: `{resultado.modelo}`" if resultado.modelo else "")
        + f" · Ejecutado: {resultado.fecha_utc} UTC"
    )

    render_metricas(resultado)
    st.divider()

    tab_resumen, tab_inc, tab_detalle, tab_desc = st.tabs(
        ["📌 Resumen", "📋 Incidencias", "🔍 Vista previa de la auditoría", "📦 Descargas"]
    )

    with tab_resumen:
        st.markdown("### Resumen ejecutivo")
        st.write(resultado.resumen)
        st.markdown("### Reglas aplicadas")
        st.write(" · ".join(f"`{r}`" for r in resultado.reglas_aplicadas))
        if resultado.metadatos:
            with st.expander("Metadatos del documento"):
                st.json(resultado.metadatos)

    with tab_inc:
        render_incidencias(resultado)

    with tab_detalle:
        render_detalle(resultado)

    with tab_desc:
        render_descargas(resultado, datos_pdf)

    render_banner_comercial()


if __name__ == "__main__":
    main()
