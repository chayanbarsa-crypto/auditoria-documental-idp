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
import csv
import io
import json
import os
import re
import smtplib
import zipfile
from email.message import EmailMessage
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

try:  # Hora peninsular: el contenedor de despliegue corre en UTC.
    from zoneinfo import ZoneInfo

    ZONA_HORARIA = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover - falta el paquete tzdata
    ZONA_HORARIA = timezone.utc

try:  # Carga ANTHROPIC_API_KEY desde .env si existe.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# 2. CONFIGURACIÓN Y CATÁLOGO DE REGLAS DE NEGOCIO
# ---------------------------------------------------------------------------

# Datos del responsable del tratamiento, obligatorios en la cláusula
# informativa (art. 13 RGPD). Recomendable añadir los apellidos: el precepto
# habla de "identidad del responsable" y el nombre de pila solo la determina
# de forma parcial.
RESPONSABLE_TRATAMIENTO = "Jordy"
EMAIL_CONTACTO_RGPD = "avc.jordy@gmail.com"
CONSERVACION_DATOS = "2 años desde el último contacto"

APP_TITLE = "📄 Módulo de Auditoría Documental Inteligente (IDP)"
APP_SUBTITLE = (
    "Procesamiento, validación y corrección automatizada de PDFs "
    "contra reglas de negocio."
)
CONTACTO_TELEFONO = "603 460 945"

# Modelo por defecto para el modo IA real.
_DIR_EJEMPLOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ejemplo")

# Documentos de demostración. El "conforme" debe dar 0 incumplimientos y el
# otro exactamente las incidencias listadas, de modo que quien los descargue
# pueda contrastar el informe con el papel.
EJEMPLOS: dict[str, dict[str, Any]] = {
    "✅ Factura conforme (sin errores)": {
        "fichero": os.path.join(_DIR_EJEMPLOS, "ejemplo_conforme.pdf"),
        "descripcion": "Todos los campos correctos. La auditoría debe dar "
        "**0 incumplimientos** y 100 % de cumplimiento.",
        "errores": [],
    },
    "⚠️ Factura con 7 errores": {
        "fichero": os.path.join(_DIR_EJEMPLOS, "ejemplo_con_errores.pdf"),
        "descripcion": "Misma factura con defectos deliberados, todos "
        "visibles a simple vista.",
        "errores": [
            "**Importes** — TOTAL 1.310,00 € cuando 1.000,00 + 210,00 = 1.210,00 €",
            "**Fechas** — fin (15/02/2026) anterior al inicio (01/03/2026)",
            "**Estructura** — Nº de factura sin rellenar: `[PENDIENTE]`",
            "**Identificadores** — CIF del emisor: `(no consta)`",
            "**Identificadores** — IBAN de 23 caracteres (los españoles tienen 24)",
            "**Firmas** — la firma del receptor está en blanco",
            "**Protección de datos** — cita la LOPD 15/1999, derogada en 2018",
        ],
    },
}

# Opción del selector que audita los dos ejemplos como un único lote: es la
# que enseña el panel agregado sin obligar a subir nada.
LOTE_EJEMPLO = "📊 Ambas a la vez (lote de 2)"

MODELO_IA = "claude-opus-5"
MAX_TOKENS_IA = 16_000

# Tope de documentos por lote. La demo pública corre en un contenedor con
# memoria contenida y, en modo IA, cada documento es una llamada a la API:
# más vale un lote pequeño que una primera impresión con un timeout.
MAX_DOCUMENTOS = 2
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
# Todas activas por defecto: así el checklist cubre los 7 errores del
# documento de ejemplo y quien lo revise ve el recuento completo.
REGLAS_POR_DEFECTO = [r.nombre for r in CATALOGO_REGLAS]


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


def leer_pdf(datos: bytes) -> tuple[list[str], dict[str, Any]]:
    """Devuelve (texto de cada página, metadatos) de un PDF en memoria.

    Prueba PyMuPDF y, si no está disponible, pypdf. Si ninguno está instalado
    devuelve valores neutros para que la demo siga siendo utilizable.
    """
    if HAS_PYMUPDF:
        with fitz.open(stream=datos, filetype="pdf") as doc:
            paginas = [pagina.get_text() for pagina in doc]
            meta = {k: v for k, v in (doc.metadata or {}).items() if v}
        return paginas, meta

    if HAS_PYPDF:
        lector = PdfReader(io.BytesIO(datos))
        paginas = [(p.extract_text() or "") for p in lector.pages]
        meta = {
            k.lstrip("/"): str(v)
            for k, v in (lector.metadata or {}).items()
            if v
        }
        return paginas, meta

    # Sin librería de PDF: estimación grosera del nº de páginas por marcadores.
    n = max(1, datos.count(b"/Type /Page") or datos.count(b"/Type/Page"))
    return [""] * n, {"aviso": "Instala pymupdf o pypdf para extraer texto."}


def extraer_campos(paginas: list[str]) -> dict[str, tuple[str, int]]:
    """Empareja «Etiqueta:» con su valor y devuelve {etiqueta: (valor, página)}.

    Los extractores de PDF devuelven la etiqueta y su valor en líneas separadas
    cuando están en columnas distintas, así que se admiten ambas formas:
    «Etiqueta: valor» en una línea y «Etiqueta:» seguida del valor en la
    siguiente. La clave se normaliza a minúsculas sin espacios sobrantes.
    """
    campos: dict[str, tuple[str, int]] = {}
    for n_pagina, texto in enumerate(paginas, start=1):
        lineas = [ln.strip() for ln in texto.splitlines()]
        for i, linea in enumerate(lineas):
            if ":" not in linea:
                continue
            etiqueta, _, resto = linea.partition(":")
            etiqueta = etiqueta.strip().lower()
            if not etiqueta or len(etiqueta) > 40:
                continue
            valor = resto.strip()
            if not valor:  # el valor viaja en la línea siguiente
                valor = lineas[i + 1].strip() if i + 1 < len(lineas) else ""
                # Si lo siguiente es otra etiqueta, este campo está vacío.
                if valor.endswith(":"):
                    valor = ""
            campos.setdefault(etiqueta, (valor, n_pagina))
    return campos


def es_pdf(datos: bytes) -> bool:
    """Comprueba la cabecera mágica del fichero."""
    return datos[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# 5. MOTOR A — REGLAS DETERMINISTAS (sin IA, sin coste)
# ---------------------------------------------------------------------------
# Cada regla inspecciona el texto realmente extraído del PDF y cita en la
# evidencia lo que ha encontrado, de forma que cualquiera pueda contrastar el
# informe contra el documento. Si un campo no aparece, la regla lo declara
# «no evaluable» en lugar de inventarse un hallazgo.

RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
RE_FECHA_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RE_IMPORTE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}")
RE_IMPORTE_ANGLOSAJON = re.compile(r"\b\d{1,3}(?:,\d{3})+\.\d{2}\b")
RE_CIF = re.compile(r"^[A-HJNP-SUVW]-?\d{7}[0-9A-J]$", re.IGNORECASE)
RE_NIF = re.compile(r"^\d{8}[A-Z]$", re.IGNORECASE)
RE_PLACEHOLDER = re.compile(
    r"\[[^\]]{0,40}(?:pendiente|pdte|rellenar|completar|tbd|por definir)[^\]]{0,40}\]|X{4,}",
    re.IGNORECASE,
)
RE_PAGINA = re.compile(r"P[áa]g(?:ina)?\.?\s*(\d+)", re.IGNORECASE)

# Valores que, apareciendo en un campo, significan «aquí no hay nada».
VALORES_VACIOS = {
    "", "-", "—", "--", "n/a", "na", "no consta", "(no consta)",
    "pendiente", "[pendiente]", "por determinar",
}


def _es_vacio(valor: str) -> bool:
    """True si el valor está en blanco o es un marcador de hueco."""
    limpio = valor.strip().lower()
    if limpio in VALORES_VACIOS:
        return True
    # Líneas de firma sin rellenar: solo guiones bajos, puntos o espacios.
    return bool(limpio) and all(c in "_.· " for c in limpio)


def _campo(campos: dict[str, tuple[str, int]], *prefijos: str) -> tuple[str, int] | None:
    """Primer campo cuya etiqueta empiece por alguno de los prefijos dados."""
    for prefijo in prefijos:
        for etiqueta, valor in campos.items():
            if etiqueta.startswith(prefijo):
                return valor
    return None


def _a_numero(texto: str) -> float | None:
    """Convierte «1.210,00 EUR» en 1210.0. None si no hay ningún importe."""
    encontrado = RE_IMPORTE.search(texto)
    if not encontrado:
        return None
    return float(encontrado.group(0).replace(".", "").replace(",", "."))


def _formato_es(numero: float) -> str:
    """1210.0 -> «1.210,00» (separador de miles y decimal españoles)."""
    return f"{numero:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def _a_fecha(texto: str) -> datetime | None:
    """Convierte la primera fecha DD/MM/AAAA encontrada; None si no hay."""
    encontrado = RE_FECHA.search(texto)
    if not encontrado:
        return None
    dia, mes, anio = (int(g) for g in encontrado.groups())
    try:
        return datetime(anio, mes, dia)
    except ValueError:  # fecha imposible, p. ej. 31/02
        return None


def _lineas_con_etiqueta(paginas: list[str], etiqueta: str) -> list[tuple[str, int]]:
    """Todos los valores de una etiqueta repetida -> [(valor, página), ...].

    `extraer_campos` se queda con la primera aparición de cada etiqueta; esta
    función sirve para las que salen varias veces (dos firmas, dos CIF...).
    """
    patron = re.compile(rf"^{re.escape(etiqueta)}\s*:?\s*(.*)$", re.IGNORECASE)
    resultados: list[tuple[str, int]] = []
    for n_pagina, texto in enumerate(paginas, start=1):
        lineas = [ln.strip() for ln in texto.splitlines()]
        for i, linea in enumerate(lineas):
            coincidencia = patron.match(linea)
            if not coincidencia:
                continue
            valor = coincidencia.group(1).strip()
            if not valor and i + 1 < len(lineas) and not lineas[i + 1].endswith(":"):
                valor = lineas[i + 1].strip()
            resultados.append((valor, n_pagina))
    return resultados


def _hallazgo(
    regla: Regla,
    pagina: int,
    severidad: str,
    descripcion: str,
    evidencia: str,
    sugerencia: str,
) -> Hallazgo:
    return Hallazgo(
        regla=regla.nombre,
        pagina=pagina,
        severidad=severidad,
        estado="No cumple",
        descripcion=descripcion,
        evidencia=evidencia,
        sugerencia=sugerencia,
    )


def _no_evaluable(regla: Regla, motivo: str) -> Hallazgo:
    """La regla no ha encontrado los campos que necesita para pronunciarse."""
    return Hallazgo(
        regla=regla.nombre,
        pagina=0,
        severidad="Informativa",
        estado="Requiere revisión",
        descripcion=f"No evaluable automáticamente: {motivo}.",
        evidencia="El motor de reglas no localiza los campos necesarios.",
        sugerencia="Revisión manual, o usa el motor de IA para documentos "
        "con estructura libre.",
    )


# --- Una función por regla -------------------------------------------------


def _regla_firmas(regla, campos, paginas, texto) -> list[Hallazgo]:
    firmas = _lineas_con_etiqueta(paginas, "Fdo.") + _lineas_con_etiqueta(paginas, "Firmado por")
    if not firmas:
        return [_no_evaluable(regla, "no se localiza ningún bloque de firma")]

    hallazgos = []
    for valor, pagina in firmas:
        if _es_vacio(valor):
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Crítica",
                    "Bloque de firma sin firmante identificado.",
                    f"Se lee «Fdo.: {valor or '(en blanco)'}».",
                    "Recabar la firma y el nombre completo del firmante.",
                )
            )
        elif not (RE_NIF.search(valor.replace(" ", "")) or "NIF" in valor.upper()):
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Media",
                    "Firma sin documento identificativo del firmante.",
                    f"Se lee «Fdo.: {valor}», sin NIF asociado.",
                    "Añadir el NIF junto al nombre del firmante.",
                )
            )
    return hallazgos


def _regla_fechas(regla, campos, paginas, texto) -> list[Hallazgo]:
    hallazgos = []
    inicio = _campo(campos, "fecha de inicio", "fecha inicio")
    fin = _campo(campos, "fecha de fin", "fecha fin", "fecha de vencimiento")

    if inicio and fin:
        f_inicio, f_fin = _a_fecha(inicio[0]), _a_fecha(fin[0])
        if f_inicio and f_fin and f_fin < f_inicio:
            hallazgos.append(
                _hallazgo(
                    regla, fin[1], "Alta",
                    "La fecha de fin es anterior a la fecha de inicio.",
                    f"Inicio {inicio[0]} — Fin {fin[0]}.",
                    "Corregir la fecha de fin o justificar el periodo.",
                )
            )
    elif not inicio and not fin:
        if not RE_FECHA.search(texto):
            return [_no_evaluable(regla, "el documento no contiene fechas")]

    if RE_FECHA_ISO.search(texto) and RE_FECHA.search(texto):
        hallazgos.append(
            _hallazgo(
                regla, 1, "Media",
                "Conviven dos formatos de fecha en el mismo documento.",
                "Se detectan DD/MM/AAAA y AAAA-MM-DD.",
                "Homogeneizar todas las fechas a DD/MM/AAAA.",
            )
        )
    return hallazgos


def _regla_importes(regla, campos, paginas, texto) -> list[Hallazgo]:
    hallazgos = []
    base = _campo(campos, "base imponible", "base")
    impuesto = _campo(campos, "iva", "igic", "impuesto")
    total = _campo(campos, "total")

    if base and impuesto and total:
        n_base, n_imp, n_total = (_a_numero(c[0]) for c in (base, impuesto, total))
        if None not in (n_base, n_imp, n_total):
            esperado = round(n_base + n_imp, 2)
            if abs(esperado - n_total) > 0.01:
                hallazgos.append(
                    _hallazgo(
                        regla, total[1], "Crítica",
                        "El total no cuadra con la suma de base imponible e impuestos.",
                        f"{base[0]} + {impuesto[0]} = {_formato_es(esperado)} EUR, "
                        f"pero el documento declara {total[0]}.",
                        f"Corregir el total: debería ser {_formato_es(esperado)} EUR.",
                    )
                )
    else:
        return [_no_evaluable(regla, "no se localizan base imponible, impuesto y total")]

    if RE_IMPORTE_ANGLOSAJON.search(texto):
        hallazgos.append(
            _hallazgo(
                regla, 1, "Baja",
                "Uso inconsistente del separador decimal.",
                f"Se detecta el formato anglosajón «{RE_IMPORTE_ANGLOSAJON.search(texto).group(0)}».",
                "Unificar al formato español: 1.234,56.",
            )
        )
    return hallazgos


def _regla_estructura(regla, campos, paginas, texto) -> list[Hallazgo]:
    hallazgos = []

    vistos: set[str] = set()
    for coincidencia in RE_PLACEHOLDER.finditer(texto):
        marcador = coincidencia.group(0)
        if marcador.lower() in vistos:
            continue
        vistos.add(marcador.lower())
        pagina = next(
            (i for i, p in enumerate(paginas, start=1) if marcador in p), 1
        )
        etiqueta = next(
            (k for k, (v, _) in campos.items() if marcador in v), None
        )
        hallazgos.append(
            _hallazgo(
                regla, pagina, "Alta",
                "Campo obligatorio sin rellenar.",
                f"Marcador «{marcador}»" + (f" en el campo «{etiqueta}»." if etiqueta else "."),
                "Completar el campo antes de dar el documento por válido.",
            )
        )

    # Continuidad de la paginación (solo si el documento la declara).
    numeros = [
        int(m.group(1))
        for pagina in paginas
        for m in [RE_PAGINA.search(pagina)]
        if m
    ]
    if len(numeros) >= 2 and numeros != list(range(numeros[0], numeros[0] + len(numeros))):
        hallazgos.append(
            _hallazgo(
                regla, 1, "Media",
                "La numeración de páginas no es continua.",
                f"Secuencia detectada: {numeros}.",
                "Regenerar el documento con paginación correlativa.",
            )
        )
    return hallazgos


def _regla_identificadores(regla, campos, paginas, texto) -> list[Hallazgo]:
    hallazgos = []
    identificadores = (
        _lineas_con_etiqueta(paginas, "CIF")
        + _lineas_con_etiqueta(paginas, "NIF")
        + _lineas_con_etiqueta(paginas, "NIF/CIF")
    )
    ibans = _lineas_con_etiqueta(paginas, "IBAN")

    if not identificadores and not ibans:
        return [_no_evaluable(regla, "no se localizan identificadores fiscales ni bancarios")]

    for valor, pagina in identificadores:
        limpio = valor.strip().replace(" ", "")
        # El vacío se evalúa sobre el valor original: «(no consta)» pierde su
        # espacio al normalizar y dejaría de reconocerse.
        if _es_vacio(valor) or _es_vacio(limpio):
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Crítica",
                    "Identificador fiscal ausente.",
                    f"Se lee «{valor or '(en blanco)'}» en lugar de un NIF/CIF.",
                    "Completar el identificador fiscal de la entidad.",
                )
            )
        elif not (RE_CIF.match(limpio) or RE_NIF.match(limpio)):
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Alta",
                    "El identificador fiscal no tiene un formato válido.",
                    f"Valor encontrado: «{valor}».",
                    "Verificar el NIF/CIF contra el censo y corregirlo.",
                )
            )

    for valor, pagina in ibans:
        limpio = valor.strip().replace(" ", "").upper()
        if _es_vacio(limpio):
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Alta", "IBAN ausente.",
                    "El campo IBAN está vacío.",
                    "Solicitar el certificado de titularidad bancaria.",
                )
            )
        elif limpio.startswith("ES") and len(limpio) != 24:
            hallazgos.append(
                _hallazgo(
                    regla, pagina, "Alta",
                    "El IBAN no tiene la longitud correcta para España.",
                    f"«{valor}» tiene {len(limpio)} caracteres; un IBAN español tiene 24.",
                    "Corregir el IBAN: faltan o sobran dígitos.",
                )
            )
    return hallazgos


def _regla_proteccion_datos(regla, campos, paginas, texto) -> list[Hallazgo]:
    normalizado = texto.upper()
    derogada = "15/1999" in normalizado or "LOPD 15" in normalizado
    vigente = "RGPD" in normalizado or "LOPDGDD" in normalizado or "3/2018" in normalizado

    if derogada:
        return [
            _hallazgo(
                regla, 1, "Alta",
                "La cláusula de protección de datos cita normativa derogada.",
                "Se menciona la LOPD 15/1999, sustituida en 2018.",
                "Actualizar la referencia al RGPD (UE) 2016/679 y la LOPDGDD 3/2018.",
            )
        ]
    if not vigente:
        return [
            _hallazgo(
                regla, 1, "Alta",
                "Falta la cláusula informativa de protección de datos.",
                "No se localiza mención al RGPD ni a la LOPDGDD.",
                "Incorporar la cláusula informativa al pie del documento.",
            )
        ]
    return []


VALIDADORES = {
    "R01": _regla_firmas,
    "R02": _regla_fechas,
    "R03": _regla_importes,
    "R04": _regla_estructura,
    "R05": _regla_identificadores,
    "R06": _regla_proteccion_datos,
}


def auditar_por_reglas(
    datos: bytes,
    nombre: str,
    paginas_texto: list[str],
    metadatos: dict[str, Any],
    reglas: list[Regla],
) -> ResultadoAuditoria:
    """Audita el documento aplicando las validaciones deterministas.

    No hay aleatoriedad ni plantillas: dos ejecuciones sobre el mismo PDF dan
    exactamente el mismo informe, y cada hallazgo cita el texto que lo motiva.
    """
    texto = "\n".join(paginas_texto)
    campos = extraer_campos(paginas_texto)

    hallazgos: list[Hallazgo] = []
    if not texto.strip():
        # PDF escaneado sin capa de texto: decirlo, no fabricar hallazgos.
        for regla in reglas:
            hallazgos.append(
                _no_evaluable(regla, "el PDF no contiene texto extraíble (¿escaneado?)")
            )
    else:
        for regla in reglas:
            validador = VALIDADORES.get(regla.id)
            if validador is None:
                continue
            hallazgos.extend(validador(regla, campos, paginas_texto, texto))

    # Las reglas que no han producido ningún hallazgo se registran como conformes.
    reglas_con_hallazgo = {h.regla for h in hallazgos}
    for regla in reglas:
        if regla.nombre not in reglas_con_hallazgo:
            hallazgos.append(
                Hallazgo(
                    regla=regla.nombre,
                    pagina=0,
                    severidad="Informativa",
                    estado="Cumple",
                    descripcion=f"Sin incidencias: «{regla.nombre}» se valida correctamente.",
                    evidencia="Todas las comprobaciones de la regla se han superado.",
                    sugerencia="",
                )
            )

    hallazgos.sort(key=lambda h: (SEVERIDADES.index(h.severidad), h.pagina))
    cumplimiento = calcular_cumplimiento(hallazgos)

    incumplimientos = [h for h in hallazgos if h.estado == "No cumple"]
    revisables = [h for h in hallazgos if h.estado == "Requiere revisión"]
    criticos = sum(1 for h in incumplimientos if h.severidad == "Crítica")

    partes = [
        f"Se han revisado {len(paginas_texto)} página(s) contra "
        f"{len(reglas)} regla(s) de negocio."
    ]
    if incumplimientos:
        partes.append(
            f"El documento alcanza un {cumplimiento} % de cumplimiento con "
            f"{len(incumplimientos)} incumplimiento(s), "
            f"{criticos} de ellos críticos."
        )
        partes.append(
            "Se recomienda subsanar las incidencias críticas antes de dar el "
            "documento por válido."
            if criticos
            else "No hay bloqueantes críticos, pero conviene corregir lo detectado."
        )
    else:
        partes.append(
            f"El documento supera todas las validaciones aplicadas "
            f"({cumplimiento} % de cumplimiento)."
        )
    if revisables:
        partes.append(
            f"{len(revisables)} regla(s) no son evaluables automáticamente y "
            "requieren revisión manual o el motor de IA."
        )

    return ResultadoAuditoria(
        documento=nombre,
        motor="Reglas deterministas (sin IA)",
        modelo=None,
        fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        paginas=len(paginas_texto),
        tamano_kb=round(len(datos) / 1024, 1),
        reglas_aplicadas=[r.nombre for r in reglas],
        cumplimiento=cumplimiento,
        resumen=" ".join(partes),
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
    paginas_texto: list[str],
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

    paginas = len(paginas_texto)
    texto = "\n".join(paginas_texto)
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
# 8. REGISTRO DE VISITAS Y CONTROL DE ACCESO
# ---------------------------------------------------------------------------
# La demo se abre solo tras identificarse. Cada visita se avisa por correo al
# responsable; el CSV local es un respaldo que únicamente sirve ejecutando en
# local, porque en Streamlit Cloud el disco del contenedor es efímero.

# La fecha y la hora no se piden: se sellan en el servidor al conceder el
# acceso. Solo se ven en el aviso por correo, nunca en la interfaz.
COLUMNAS_LEAD = [
    "fecha",
    "hora",
    "nombre",
    "empresa",
    "sector",
    "email",
    "cargo",
    "interes",
    "consentimiento_comercial",
    "origen",
]

SECTORES = [
    "Asesoría / Gestoría",
    "Banca y seguros",
    "Construcción e inmobiliaria",
    "Consultoría",
    "Educación",
    "Energía y utilities",
    "Industria y fabricación",
    "Legal / Despacho de abogados",
    "Logística y transporte",
    "Retail y distribución",
    "Sanidad y farmacéutica",
    "Sector público",
    "Tecnología / Software",
    "Turismo y hostelería",
    "Otro",
]

INTERESES = [
    "Curiosidad profesional / evaluación técnica",
    "Proceso de selección (soy reclutador)",
    "Posible implantación en mi empresa",
    "Otro",
]

RUTA_LEADS_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "leads_local.csv"
)

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _cuerpo_email(lead: dict[str, str]) -> str:
    """Texto del aviso, con los campos alineados para leerlo de un vistazo."""
    etiquetas = {
        "fecha": "Fecha",
        "hora": "Hora",
        "nombre": "Nombre",
        "empresa": "Empresa",
        "sector": "Sector",
        "email": "Email",
        "cargo": "Cargo",
        "interes": "Motivo",
        "origen": "Origen",
        "consentimiento_comercial": "Consiente contacto",
    }
    ancho = max(len(e) for e in etiquetas.values())
    lineas = [
        f"{etiqueta.ljust(ancho)} : {lead.get(clave) or '—'}"
        for clave, etiqueta in etiquetas.items()
    ]
    return (
        "Alguien acaba de entrar en la demo de auditoría documental.\n\n"
        + "\n".join(lineas)
        + "\n\nPuedes responder directamente a este correo para contactar "
        "con la persona.\n"
    )


def _enviar_aviso(lead: dict[str, str]) -> bool:
    """Envía el aviso por SMTP. False si no hay configuración o falla el envío."""
    try:
        configuracion = st.secrets["email"]
        remitente = configuracion["remitente"]
        contrasena = configuracion["password_app"]
        destinatario = configuracion.get("destinatario", remitente)
        servidor = configuracion.get("servidor", "smtp.gmail.com")
        puerto = int(configuracion.get("puerto", 465))
    except Exception:
        return False  # sin secrets configurados: se usará el CSV

    mensaje = EmailMessage()
    mensaje["Subject"] = (
        f"🔔 Demo IDP — {lead.get('empresa', '?')} ({lead.get('sector', '?')})"
    )
    mensaje["From"] = remitente
    mensaje["To"] = destinatario
    if lead.get("email"):
        # Responder al aviso escribe directamente al visitante.
        mensaje["Reply-To"] = lead["email"]
    mensaje.set_content(_cuerpo_email(lead))

    try:
        with smtplib.SMTP_SSL(servidor, puerto, timeout=15) as smtp:
            smtp.login(remitente, contrasena)
            smtp.send_message(mensaje)
        return True
    except Exception as exc:
        print(f"[registro] fallo al enviar el aviso por correo: {exc}")
        return False


def registrar_lead(lead: dict[str, str]) -> str:
    """Persiste el lead y devuelve el destino usado: email | csv | log.

    Nunca lanza: si el registro falla, el visitante no debe quedarse fuera por
    un problema de nuestra infraestructura. El peor caso deja el lead en los
    logs del servidor, desde donde se puede recuperar a mano.
    """
    fila = [lead.get(columna, "") for columna in COLUMNAS_LEAD]

    if _enviar_aviso(lead):
        return "email"

    try:
        nuevo = not os.path.exists(RUTA_LEADS_CSV)
        with open(RUTA_LEADS_CSV, "a", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.writer(fh, delimiter=";")
            if nuevo:
                escritor.writerow(COLUMNAS_LEAD)
            escritor.writerow(fila)
        return "csv"
    except Exception as exc:
        print(f"[registro] fallo al escribir el CSV local: {exc}")

    # Último recurso: que quede constancia en el log del servidor.
    print(f"[registro] LEAD SIN PERSISTIR -> {dict(zip(COLUMNAS_LEAD, fila))}")
    return "log"


def acceso_concedido() -> bool:
    """True si esta sesión del navegador ya se ha identificado.

    `DEMO_SIN_REGISTRO=1` salta la puerta: es una variable de entorno para
    desarrollo y pruebas en local. En Streamlit Cloud no está definida, así
    que la demo publicada siempre pide el registro.
    """
    if os.getenv("DEMO_SIN_REGISTRO") == "1":
        return True
    return bool(st.session_state.get("acceso_concedido"))


def _validar(
    nombre: str, empresa: str, sector: str | None, email: str, consiente: bool
) -> list[str]:
    """Lista de errores del formulario; vacía si todo es correcto."""
    errores = []
    if len(nombre.strip()) < 3:
        errores.append("**Nombre y apellidos** — indica tu nombre completo.")
    if len(empresa.strip()) < 2:
        errores.append("**Empresa u organización** — este campo es obligatorio.")
    if not sector:
        errores.append("**Sector** — selecciona uno de la lista.")
    if not RE_EMAIL.match(email.strip()):
        errores.append("**Correo electrónico** — el formato no es válido.")
    if not consiente:
        errores.append(
            "**Protección de datos** — debes aceptar el tratamiento para continuar."
        )
    return errores


def render_banner_faltan_datos(errores: list[str]) -> None:
    """Banner destacado cuando el formulario está incompleto."""
    st.markdown(
        f"""
<div style="
    background: #7f1d1d;
    border-left: 6px solid #f87171;
    color: #fee2e2;
    padding: 16px 20px;
    border-radius: 10px;
    margin-bottom: 8px;
">
  <div style="font-size:1.05rem; font-weight:700; margin-bottom:4px;">
    🚫 No se puede acceder: faltan datos obligatorios
  </div>
  <div style="font-size:0.94rem; opacity:0.95;">
    Completa {len(errores)} campo(s) para desbloquear la demostración.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    for error in errores:
        st.error(error)


def render_clausula_privacidad() -> None:
    """Cláusula informativa del art. 13 RGPD."""
    incompleta = "COMPLETAR" in RESPONSABLE_TRATAMIENTO
    if incompleta:
        st.warning(
            "⚠️ Cláusula incompleta: falta identificar al responsable del "
            "tratamiento en `RESPONSABLE_TRATAMIENTO` (app.py)."
        )
    st.markdown(
        f"""
**Responsable:** {RESPONSABLE_TRATAMIENTO}

**Finalidad:** registrar el uso de esta demostración y ponerse en contacto
contigo si has mostrado interés comercial. No se elaboran perfiles ni se toman
decisiones automatizadas.

**Legitimación:** tu consentimiento expreso, que puedes retirar en cualquier
momento.

**Destinatarios:** no se ceden a terceros. Los datos se envían por correo
electrónico al buzón del responsable, alojado en Gmail (Google Ireland Ltd.,
proveedor de correo).

**Conservación:** {CONSERVACION_DATOS}.

**Derechos:** puedes acceder, rectificar, suprimir, limitar u oponerte al
tratamiento y solicitar su portabilidad escribiendo a **{EMAIL_CONTACTO_RGPD}**.
También puedes reclamar ante la Agencia Española de Protección de Datos
(www.aepd.es).

**Los documentos que subas a la demo no se almacenan**: se procesan en memoria
y se descartan al terminar la sesión.
"""
    )


def render_puerta() -> None:
    """Formulario de acceso. Sin él no se llega a la aplicación."""
    st.info(
        "🔒 **Demostración con acceso registrado.** Identifícate para probar la "
        "herramienta. Es un formulario de 30 segundos y no se envía ningún "
        "correo automático."
    )

    c1, c2, c3 = st.columns(3)
    c1.markdown(
        "#### Qué vas a poder hacer\n"
        "Auditar hasta dos PDFs contra un checklist de reglas de negocio, con "
        "documentos de ejemplo incluidos."
    )
    c2.markdown(
        "#### Sin coste ni claves\n"
        "El motor de reglas funciona sin API de pago. Los documentos se "
        "procesan en memoria y no se almacenan."
    )
    c3.markdown(
        "#### Qué obtienes\n"
        "Informe de incidencias con evidencia, JSON estructurado, CSV del lote "
        "y los documentos corregidos."
    )

    st.divider()

    with st.form("registro_acceso", clear_on_submit=False):
        st.markdown("#### Datos de acceso")
        st.caption("Los campos marcados con * son obligatorios.")
        col_a, col_b = st.columns(2)
        nombre = col_a.text_input("Nombre y apellidos *", max_chars=120)
        empresa = col_b.text_input("Empresa u organización *", max_chars=120)
        col_c, col_d = st.columns(2)
        sector = col_c.selectbox(
            "Sector *",
            options=SECTORES,
            index=None,
            placeholder="Selecciona el sector…",
        )
        email = col_d.text_input("Correo electrónico *", max_chars=160)
        col_e, col_f = st.columns(2)
        cargo = col_e.text_input("Cargo (opcional)", max_chars=120)
        interes = col_f.selectbox("¿Qué te trae por aquí?", options=INTERESES)

        with st.expander("Información sobre protección de datos (léelo antes de aceptar)"):
            render_clausula_privacidad()

        consiente = st.checkbox(
            "He leído la información sobre protección de datos y **consiento** "
            "el tratamiento de mis datos para que se contacte conmigo.",
            value=False,
        )

        enviado = st.form_submit_button(
            "🔓 Acceder a la demostración", type="primary", width="stretch"
        )

    if not enviado:
        return

    errores = _validar(nombre, empresa, sector, email, consiente)
    if errores:
        render_banner_faltan_datos(errores)
        return

    # Marca temporal del servidor en hora peninsular: el visitante no la
    # introduce ni la ve, solo aparece en el aviso que se envía por correo.
    ahora = datetime.now(ZONA_HORARIA)
    lead = {
        "fecha": ahora.strftime("%d/%m/%Y"),
        "hora": ahora.strftime("%H:%M:%S"),
        "nombre": nombre.strip(),
        "empresa": empresa.strip(),
        "sector": sector,
        "email": email.strip().lower(),
        "cargo": cargo.strip(),
        "interes": interes,
        "consentimiento_comercial": "sí",
        # Permite medir de dónde llega la visita: ?origen=linkedin, ?origen=cv...
        "origen": st.query_params.get("origen", "directo"),
    }
    destino = registrar_lead(lead)
    if destino == "log":
        print("[registro] revisa la configuración: el lead no se ha persistido")

    st.session_state["acceso_concedido"] = True
    st.session_state["visitante"] = lead
    st.rerun()


# ---------------------------------------------------------------------------
# 9. INTERFAZ — BARRA LATERAL
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

        st.subheader("2. Documentos")
        ficheros = st.file_uploader(
            f"Sube hasta {MAX_DOCUMENTOS} PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="Se procesan en memoria; no se almacenan en disco. Con dos "
            "documentos verás además el panel agregado del lote.",
        ) or []

        # Streamlit no sabe limitar el número de ficheros, así que se valida
        # aquí: mejor bloquear el análisis que recortar en silencio la
        # selección del usuario.
        exceso = len(ficheros) > MAX_DOCUMENTOS
        if exceso:
            st.error(
                f"Has seleccionado {len(ficheros)} documentos. Esta demo admite "
                f"un máximo de {MAX_DOCUMENTOS}; el procesamiento en lote sin "
                "límite forma parte de la versión completa."
            )

        # Ejemplos: permiten probarlo sin traer ficheros propios, y el lote de
        # dos enseña el panel agregado.
        disponibles = {
            k: v for k, v in EJEMPLOS.items() if os.path.exists(v["fichero"])
        }
        ejemplo = None
        if disponibles:
            opciones = [None, *disponibles.keys()]
            if len(disponibles) >= 2:
                opciones.append(LOTE_EJEMPLO)
            ejemplo = st.selectbox(
                "…o usa los documentos de ejemplo",
                options=opciones,
                format_func=lambda x: "— ninguno —" if x is None else x,
                disabled=bool(ficheros),
                help="Facturas de una página, pensadas para revisarlas a "
                "simple vista y contrastar el informe.",
            )
            if ficheros:
                ejemplo = None

            if ejemplo == LOTE_EJEMPLO:
                st.caption(
                    "Audita las dos facturas de golpe y muestra el **panel "
                    "agregado**: cumplimiento medio, ranking de documentos y "
                    "qué regla concentra los fallos del lote."
                )
                for info in disponibles.values():
                    with open(info["fichero"], "rb") as fh:
                        st.download_button(
                            f"⬇️ {os.path.basename(info['fichero'])}",
                            data=fh.read(),
                            file_name=os.path.basename(info["fichero"]),
                            mime="application/pdf",
                            width="stretch",
                        )
            elif ejemplo:
                info = disponibles[ejemplo]
                st.caption(info["descripcion"])
                with open(info["fichero"], "rb") as fh:
                    st.download_button(
                        "⬇️ Descargar este PDF para revisarlo",
                        data=fh.read(),
                        file_name=os.path.basename(info["fichero"]),
                        mime="application/pdf",
                        width="stretch",
                    )
                if info["errores"]:
                    with st.expander(f"Ver los {len(info['errores'])} errores que contiene"):
                        for i, err in enumerate(info["errores"], start=1):
                            st.markdown(f"{i}. {err}")

        st.subheader("3. Motor de análisis")
        motor = st.radio(
            "Modo de ejecución",
            options=["Reglas deterministas", "IA real (API Anthropic)"],
            captions=[
                "Valida el texto del PDF. Sin clave ni coste.",
                f"Análisis con {MODELO_IA}. Requiere clave propia.",
            ],
            index=0,
        )

        n_documentos = len(ficheros) or (
            len(EJEMPLOS) if ejemplo == LOTE_EJEMPLO else (1 if ejemplo else 0)
        )

        api_key = ""
        if motor.startswith("IA real"):
            if not HAS_ANTHROPIC:
                st.warning("Instala el SDK: `pip install anthropic`")
            if n_documentos > 1:
                st.warning(
                    f"El lote son {n_documentos} llamadas a la API, una por "
                    "documento: el coste se multiplica."
                )
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                st.success("Clave detectada en el entorno (ANTHROPIC_API_KEY).")
            else:
                api_key = st.text_input(
                    "ANTHROPIC_API_KEY",
                    type="password",
                    help="No se guarda: vive solo en la sesión del navegador.",
                )

        hay_documento = n_documentos > 0 and not exceso

        st.divider()
        lanzar = st.button(
            "🚀 Ejecutar auditoría"
            + (f" ({n_documentos} documentos)" if n_documentos > 1 else ""),
            type="primary",
            width="stretch",
            disabled=not hay_documento or not nombres,
        )
        if exceso:
            st.caption(f"Deja como máximo {MAX_DOCUMENTOS} documentos para continuar.")
        elif not n_documentos:
            st.caption("Sube un PDF o elige un documento de ejemplo.")
        elif not nombres:
            st.caption("Selecciona al menos una regla del checklist.")

        st.divider()
        visitante = st.session_state.get("visitante") or {}
        if visitante:
            st.caption(
                f"Sesión de **{visitante.get('nombre', '')}** "
                f"({visitante.get('empresa', '')})"
            )
        st.caption("Demo de portfolio · Procesamiento inteligente de documentos")

    return {
        "reglas": [REGLAS_POR_NOMBRE[n] for n in nombres],
        "ficheros": ficheros,
        "ejemplo": ejemplo,
        "motor": motor,
        "api_key": api_key,
        "lanzar": lanzar,
    }


def obtener_documentos(config: dict[str, Any]) -> list[tuple[str, bytes]]:
    """Lista de (nombre, bytes) a auditar: los subidos o los de ejemplo."""
    ficheros = config.get("ficheros") or []
    if ficheros:
        return [(f.name, f.getvalue()) for f in ficheros[:MAX_DOCUMENTOS]]

    clave = config.get("ejemplo")
    if not clave:
        return []

    rutas: list[str] = []
    if clave == LOTE_EJEMPLO:
        rutas = [v["fichero"] for v in EJEMPLOS.values()]
    elif clave in EJEMPLOS:
        rutas = [EJEMPLOS[clave]["fichero"]]

    documentos = []
    for ruta in rutas[:MAX_DOCUMENTOS]:
        if os.path.exists(ruta):
            with open(ruta, "rb") as fh:
                documentos.append((os.path.basename(ruta), fh.read()))
    return documentos


# ---------------------------------------------------------------------------
# 10. INTERFAZ — PANEL DE RESULTADOS
# ---------------------------------------------------------------------------


def render_metricas(res: ResultadoAuditoria) -> None:
    """Fila de KPIs del cuadro de mando."""
    abiertas = [h for h in res.hallazgos if h.estado == "No cumple"]
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


# --- Vistas de lote --------------------------------------------------------


def resumen_lote(resultados: list[ResultadoAuditoria]) -> pd.DataFrame:
    """Una fila por documento, ordenada de peor a mejor cumplimiento."""
    filas = []
    for res in resultados:
        incumplimientos = [h for h in res.hallazgos if h.estado == "No cumple"]
        peor = min(
            (SEVERIDADES.index(h.severidad) for h in incumplimientos),
            default=len(SEVERIDADES) - 1,
        )
        filas.append(
            {
                "Estado": "✅ Conforme" if not incumplimientos else "❌ Con incidencias",
                "Documento": res.documento,
                "Páginas": res.paginas,
                "Cumplimiento": res.cumplimiento,
                "Incidencias": len(incumplimientos),
                "Severidad máxima": SEVERIDADES[peor] if incumplimientos else "—",
            }
        )
    return pd.DataFrame(filas).sort_values("Cumplimiento").reset_index(drop=True)


def render_lote(resultados: list[ResultadoAuditoria]) -> None:
    """Panel agregado: lo que solo se ve cuando hay más de un documento."""
    total_incidencias = sum(
        1 for res in resultados for h in res.hallazgos if h.estado == "No cumple"
    )
    conformes = sum(
        1
        for res in resultados
        if not any(h.estado == "No cumple" for h in res.hallazgos)
    )
    medio = round(sum(r.cumplimiento for r in resultados) / len(resultados))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documentos procesados", len(resultados))
    c2.metric("Cumplimiento medio", f"{medio} %")
    c3.metric("Conformes", f"{conformes} de {len(resultados)}")
    c4.metric("Incidencias totales", total_incidencias)

    st.markdown("### Ranking de documentos")
    st.caption("Ordenado de menor a mayor cumplimiento: arriba, lo que hay que revisar antes.")
    st.dataframe(
        resumen_lote(resultados),
        width="stretch",
        hide_index=True,
        column_config={
            "Cumplimiento": st.column_config.ProgressColumn(
                "Cumplimiento", format="%d %%", min_value=0, max_value=100
            ),
            "Páginas": st.column_config.NumberColumn(width="small"),
            "Incidencias": st.column_config.NumberColumn(width="small"),
        },
    )

    # El dato que solo aparece con volumen: dónde se concentran los fallos.
    conteo: dict[str, int] = {}
    for res in resultados:
        for h in res.hallazgos:
            if h.estado == "No cumple":
                conteo[h.regla] = conteo.get(h.regla, 0) + 1
    if conteo:
        st.markdown("### Incidencias por regla en todo el lote")
        st.caption(
            "Con volumen real, este gráfico es el que dice dónde atacar primero: "
            "la regla que más se repite suele ser un problema de proceso, no del documento."
        )
        serie = pd.Series(conteo).sort_values(ascending=False)
        st.bar_chart(serie, height=240)


def render_descargas_lote(
    resultados: list[ResultadoAuditoria], documentos: list[tuple[str, bytes]]
) -> None:
    """Entregables consolidados del lote: CSV, JSON y ZIP de corregidos."""
    c1, c2, c3 = st.columns(3)

    csv = resumen_lote(resultados).to_csv(index=False, sep=";").encode("utf-8-sig")
    c1.download_button(
        "⬇️ Resumen del lote (CSV)",
        data=csv,
        file_name="auditoria_lote_resumen.csv",
        mime="text/csv",
        width="stretch",
        help="Separador ';' y BOM: se abre directamente en Excel en español.",
    )

    consolidado = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documentos": len(resultados),
        "cumplimiento_medio": round(
            sum(r.cumplimiento for r in resultados) / len(resultados)
        ),
        "auditorias": [r.to_dict() for r in resultados],
    }
    c2.download_button(
        "⬇️ Reporte consolidado (JSON)",
        data=json.dumps(consolidado, indent=2, ensure_ascii=False).encode("utf-8"),
        file_name="auditoria_lote.json",
        mime="application/json",
        width="stretch",
    )

    # ZIP con los documentos corregidos: el entregable natural de un lote.
    buffer = io.BytesIO()
    incluidos = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for res, (_, datos) in zip(resultados, documentos):
            corregido = construir_pdf_corregido(datos, res)
            if corregido:
                zf.writestr(f"corregido_{nombre_base(res.documento)}.pdf", corregido)
                incluidos += 1
        zf.writestr(
            "resumen.csv", resumen_lote(resultados).to_csv(index=False, sep=";")
        )

    if incluidos:
        c3.download_button(
            "⬇️ Documentos corregidos (ZIP)",
            data=buffer.getvalue(),
            file_name="auditoria_lote_corregidos.zip",
            mime="application/zip",
            width="stretch",
        )
    else:
        c3.button(
            "⬇️ Documentos corregidos (ZIP)",
            disabled=True,
            width="stretch",
            help="Requiere reportlab: pip install reportlab",
        )


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
    Procesamiento en lote sin límite, conciliación entre documentos,
    integración vía API con CRM/ERP o reglas personalizadas.
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
# 11. APLICACIÓN
# ---------------------------------------------------------------------------


def ejecutar_auditoria(config: dict[str, Any]) -> None:
    """Orquesta lectura y análisis de todos los documentos del lote."""
    documentos = obtener_documentos(config)
    if not documentos:
        st.error("No hay ningún documento seleccionado.")
        return

    usa_ia = config["motor"].startswith("IA real")
    if usa_ia and not config["api_key"]:
        st.error(
            "Introduce tu ANTHROPIC_API_KEY en la barra lateral o defínela "
            "como variable de entorno."
        )
        return

    if not HAS_PYMUPDF and not HAS_PYPDF:
        st.warning(
            "Sin `pymupdf` ni `pypdf` instalados: la extracción de texto es "
            "limitada. Instala uno de los dos para un análisis completo."
        )

    etiqueta = (
        "Procesando documento…"
        if len(documentos) == 1
        else f"Procesando lote de {len(documentos)} documentos…"
    )
    resultados: list[ResultadoAuditoria] = []
    procesados: list[tuple[str, bytes]] = []

    with st.status(etiqueta, expanded=True) as estado:
        for indice, (nombre, datos) in enumerate(documentos, start=1):
            prefijo = f"[{indice}/{len(documentos)}] " if len(documentos) > 1 else ""

            if not es_pdf(datos):
                st.write(f"{prefijo}⚠️ «{nombre}» no es un PDF válido; se omite.")
                continue

            st.write(f"{prefijo}📖 Extrayendo texto de «{nombre}»…")
            try:
                paginas_texto, metadatos = leer_pdf(datos)
            except Exception as exc:
                st.write(f"{prefijo}⚠️ No se ha podido leer «{nombre}»: {exc}")
                continue

            st.write(
                f"{prefijo}🔎 Aplicando {len(config['reglas'])} regla(s) sobre "
                f"{len(paginas_texto)} página(s)…"
            )
            try:
                if usa_ia:
                    st.write(f"{prefijo}🤖 Consultando al modelo {MODELO_IA}…")
                    resultado = auditar_con_ia(
                        datos, nombre, paginas_texto, metadatos,
                        config["reglas"], config["api_key"],
                    )
                else:
                    resultado = auditar_por_reglas(
                        datos, nombre, paginas_texto, metadatos, config["reglas"]
                    )
            except Exception as exc:
                # Un documento problemático no debe tumbar el lote entero.
                st.write(f"{prefijo}⚠️ Fallo al auditar «{nombre}»: {exc}")
                continue

            resultados.append(resultado)
            procesados.append((nombre, datos))

        if not resultados:
            estado.update(label="No se ha podido auditar ningún documento", state="error")
            st.error(
                "Ninguno de los documentos ha podido procesarse. Revisa que sean "
                "PDFs válidos."
            )
            return

        if len(resultados) < len(documentos):
            st.warning(
                f"Se han auditado {len(resultados)} de {len(documentos)} documentos; "
                "los demás se han omitido por los motivos indicados arriba."
            )

        st.write("🧾 Consolidando hallazgos y entregables…")
        estado.update(label="Auditoría completada", state="complete", expanded=False)

    st.session_state["resultados"] = resultados
    st.session_state["documentos"] = procesados


def main() -> None:
    st.set_page_config(
        page_title="Auditoría Documental Inteligente (IDP)",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    # Puerta de acceso: sin identificarse no se llega ni a la barra lateral.
    if not acceso_concedido():
        render_puerta()
        render_banner_comercial()
        return

    config = render_sidebar()

    if config["lanzar"]:
        ejecutar_auditoria(config)

    resultados: list[ResultadoAuditoria] = st.session_state.get("resultados") or []
    documentos: list[tuple[str, bytes]] = st.session_state.get("documentos") or []

    if not resultados or not documentos:
        # Estado inicial: explica la propuesta de valor antes del primer análisis.
        st.info(
            "👈 **Para probarlo:** elige los documentos de ejemplo en la barra "
            "lateral, descárgalos para verlos con tus propios ojos y pulsa "
            "**Ejecutar auditoría**. Podrás contrastar cada hallazgo del informe "
            f"con el papel. Admite hasta {MAX_DOCUMENTOS} documentos a la vez y "
            "no hace falta clave de API."
        )
        c1, c2, c3 = st.columns(3)
        c1.markdown(
            "#### 1. Ingesta\n"
            "Lectura de los PDFs en memoria: páginas, texto y metadatos. "
            "Sin persistencia en disco."
        )
        c2.markdown(
            "#### 2. Validación\n"
            "Cada regla de negocio se contrasta contra el documento y genera "
            "hallazgos anclados a página, con severidad y evidencia."
        )
        c3.markdown(
            "#### 3. Entregables\n"
            "Reporte JSON para integrar en tu ERP/CRM, CSV del lote y "
            "documentos corregidos con el informe anexado."
        )
        render_banner_comercial()
        return

    # --- Vista de lote: solo cuando hay más de un documento ---------------
    if len(resultados) > 1:
        st.subheader(f"Resultados del lote — {len(resultados)} documentos")
        st.caption(
            f"Motor: **{resultados[0].motor}**"
            + (f" · Modelo: `{resultados[0].modelo}`" if resultados[0].modelo else "")
            + f" · Ejecutado: {resultados[0].fecha_utc} UTC"
        )
        render_lote(resultados)
        st.divider()
        st.markdown("### Entregables del lote")
        render_descargas_lote(resultados, documentos)
        st.divider()
        st.markdown("### Detalle por documento")
        # De peor a mejor: al abrirse muestra el documento más problemático,
        # que es el que alguien querría inspeccionar primero.
        orden = sorted(
            range(len(resultados)), key=lambda i: resultados[i].cumplimiento
        )
        elegido = st.selectbox(
            "Documento a inspeccionar",
            options=orden,
            format_func=lambda i: f"{resultados[i].documento} — "
            f"{resultados[i].cumplimiento} % de cumplimiento",
        )
        resultado = resultados[elegido]
        datos_pdf = documentos[elegido][1]
    else:
        resultado = resultados[0]
        datos_pdf = documentos[0][1]
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
