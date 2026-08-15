"""Genera los dos PDFs de demostración que se ofrecen en la app.

- ejemplo_conforme.pdf     : documento correcto. La auditoría debe dar 0 errores.
- ejemplo_con_errores.pdf  : mismo documento con 7 defectos deliberados, todos
                             visibles a simple vista para que quien lo revise
                             pueda contrastar el informe con el papel.

Ambos caben en una sola página a propósito: la demo se valida de un vistazo.

Uso:  python generar_ejemplos.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

DIRECTORIO = Path(__file__).parent / "ejemplo"
ANCHO, ALTO = A4
MARGEN = 20 * mm

# (etiqueta, valor_correcto, valor_defectuoso_o_None)
# None en la tercera posición = el valor no cambia entre los dos documentos.
CAMPOS: list[tuple[str, str, str | None]] = [
    ("__seccion__", "DATOS DE LA FACTURA", None),
    ("Nº de factura", "FAC-2026-0087", "[PENDIENTE]"),
    ("Fecha de emisión", "12/02/2026", None),
    ("__seccion__", "EMISOR", None),
    ("Razón social", "Servicios Técnicos del Norte, S.L.", None),
    ("CIF", "B12345678", "(no consta)"),
    ("IBAN", "ES9121000418450200051332", "ES912100041845020005133"),
    ("__seccion__", "RECEPTOR", None),
    ("Razón social", "Distribuciones Peninsulares, S.L.", None),
    ("CIF", "B87654321", None),
    ("__seccion__", "PERIODO DE PRESTACIÓN", None),
    ("Fecha de inicio", "01/01/2026", "01/03/2026"),
    ("Fecha de fin", "31/01/2026", "15/02/2026"),
    ("__seccion__", "IMPORTES", None),
    ("Base imponible", "1.000,00 EUR", None),
    ("IVA (21%)", "210,00 EUR", None),
    ("TOTAL", "1.210,00 EUR", "1.310,00 EUR"),
    ("__seccion__", "PROTECCIÓN DE DATOS", None),
    (
        "Normativa aplicable",
        "RGPD (UE) 2016/679 y LOPDGDD 3/2018",
        "LOPD 15/1999",
    ),
]

FIRMA_EMISOR = ("Fdo.", "María López Herrera (NIF 12345678Z)", None)
FIRMA_RECEPTOR = ("Fdo.", "Carlos Ruiz Vidal (NIF 87654321X)", "____________________")


def construir(ruta: Path, con_errores: bool) -> None:
    """Dibuja el PDF; `con_errores` elige la columna de valores defectuosos."""
    c = canvas.Canvas(str(ruta), pagesize=A4)
    c.setTitle(
        "Factura de ejemplo — con errores" if con_errores else "Factura de ejemplo — conforme"
    )
    c.setAuthor("Demo IDP")

    y = ALTO - MARGEN

    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGEN, y, "FACTURA DE SERVICIOS PROFESIONALES")
    y -= 8 * mm
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        MARGEN,
        y,
        "Documento de ejemplo para la demo de auditoría documental (IDP).",
    )
    y -= 10 * mm

    for etiqueta, correcto, defectuoso in CAMPOS:
        if etiqueta == "__seccion__":
            y -= 3 * mm
            c.setFont("Helvetica-Bold", 11)
            c.drawString(MARGEN, y, correcto)
            y -= 6 * mm
            continue

        valor = defectuoso if (con_errores and defectuoso is not None) else correcto
        c.setFont("Helvetica", 10)
        c.drawString(MARGEN + 4 * mm, y, f"{etiqueta}:")
        c.setFont("Helvetica-Bold" if etiqueta == "TOTAL" else "Helvetica", 10)
        c.drawString(MARGEN + 55 * mm, y, valor)
        y -= 6 * mm

    # --- Firmas -----------------------------------------------------------
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGEN, y, "FIRMAS")
    y -= 8 * mm

    for rol, (etiqueta, correcto, defectuoso) in (
        ("Por el emisor", FIRMA_EMISOR),
        ("Por el receptor", FIRMA_RECEPTOR),
    ):
        valor = defectuoso if (con_errores and defectuoso is not None) else correcto
        c.setFont("Helvetica", 9)
        c.drawString(MARGEN + 4 * mm, y, rol)
        y -= 5 * mm
        c.setFont("Helvetica", 10)
        c.drawString(MARGEN + 4 * mm, y, f"{etiqueta}: {valor}")
        y -= 9 * mm

    # --- Pie --------------------------------------------------------------
    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, 15 * mm, "Pág. 1 de 1")

    c.save()


def main() -> None:
    DIRECTORIO.mkdir(parents=True, exist_ok=True)

    conforme = DIRECTORIO / "ejemplo_conforme.pdf"
    con_errores = DIRECTORIO / "ejemplo_con_errores.pdf"

    construir(conforme, con_errores=False)
    construir(con_errores, con_errores=True)

    for ruta in (conforme, con_errores):
        print(f"Generado: {ruta.name}  ({ruta.stat().st_size / 1024:.1f} KB)")

    # Limpia el ejemplo anterior de tres páginas, ya sustituido.
    antiguo = DIRECTORIO / "contrato_demo.pdf"
    if antiguo.exists():
        antiguo.unlink()
        print(f"Eliminado obsoleto: {antiguo.name}")


if __name__ == "__main__":
    main()
