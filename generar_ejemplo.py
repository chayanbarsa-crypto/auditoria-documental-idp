"""Genera el PDF de ejemplo que se ofrece en la demo.

El documento incluye errores deliberados (cuadre de importes incorrecto,
fechas invertidas, campo sin rellenar, firma ausente) para que la auditoría
tenga algo real que detectar.

Uso:  python generar_ejemplo.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

SALIDA = Path(__file__).parent / "ejemplo" / "contrato_demo.pdf"

ANCHO, ALTO = A4
MARGEN = 22 * mm


def linea(c: canvas.Canvas, y: float, texto: str, negrita: bool = False, tam: int = 10) -> float:
    c.setFont("Helvetica-Bold" if negrita else "Helvetica", tam)
    c.drawString(MARGEN, y, texto)
    return y - (tam + 5)


def main() -> None:
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(SALIDA), pagesize=A4)
    c.setTitle("Contrato de prestación de servicios (documento de ejemplo)")
    c.setAuthor("Demo IDP")

    # --- Página 1: cabecera y partes -------------------------------------
    y = ALTO - MARGEN
    y = linea(c, y, "CONTRATO DE PRESTACIÓN DE SERVICIOS PROFESIONALES", True, 13)
    y = linea(c, y, "Documento de ejemplo — contiene errores deliberados", False, 8)
    y -= 10
    y = linea(c, y, "Nº de expediente: [PENDIENTE]", False)  # campo sin rellenar
    y = linea(c, y, "Fecha de emisión: 14/03/2026", False)
    y -= 8
    y = linea(c, y, "PARTE CONTRATANTE", True)
    y = linea(c, y, "Razón social: Distribuciones Peninsulares, S.L.")
    y = linea(c, y, "CIF: B-12345678")
    y = linea(c, y, "Domicilio: C/ Mayor 14, 28013 Madrid")
    y -= 8
    y = linea(c, y, "PARTE PRESTADORA", True)
    y = linea(c, y, "Nombre: Servicios Técnicos del Norte, S.L.")
    y = linea(c, y, "CIF: (no consta)")  # identificador ausente
    y = linea(c, y, "IBAN: ES91 2100 0418 4502 0005 133")  # IBAN corto
    y -= 8
    y = linea(c, y, "OBJETO DEL CONTRATO", True)
    y = linea(c, y, "Prestación de servicios de consultoría técnica y mantenimiento")
    y = linea(c, y, "preventivo de la infraestructura descrita en el Anexo II.")
    linea(c, MARGEN, "Pág. 1")
    c.showPage()

    # --- Página 2: vigencia e importes ------------------------------------
    y = ALTO - MARGEN
    y = linea(c, y, "CLÁUSULA SEGUNDA — VIGENCIA", True, 12)
    y = linea(c, y, "Fecha de inicio: 01/09/2025")
    y = linea(c, y, "Fecha de fin: 15/08/2025")  # anterior al inicio
    y = linea(c, y, "Prórroga automática: sí, por periodos anuales")
    y -= 12
    y = linea(c, y, "CLÁUSULA TERCERA — CONDICIONES ECONÓMICAS", True, 12)
    y = linea(c, y, "Base imponible ............. 1.240,00 EUR")
    y = linea(c, y, "IVA (21 %) ................. 260,40 EUR")
    y = linea(c, y, "TOTAL ...................... 1.520,40 EUR")  # no cuadra
    y -= 6
    y = linea(c, y, "Forma de pago: transferencia a 30 dias fecha factura", False, 9)
    y = linea(c, y, "Importe anticipado: 1,240.00 EUR", False, 9)  # formato mixto
    linea(c, MARGEN, "Pág. 2")
    c.showPage()

    # --- Página 4 (salto deliberado): firmas ------------------------------
    y = ALTO - MARGEN
    y = linea(c, y, "CLÁUSULA OCTAVA — PROTECCIÓN DE DATOS", True, 12)
    y = linea(c, y, "Los datos serán tratados conforme a la LOPD 15/1999.", False, 9)
    y -= 20
    y = linea(c, y, "Y EN PRUEBA DE CONFORMIDAD, las partes firman el presente", False)
    y = linea(c, y, "contrato por duplicado en el lugar y fecha indicados.", False)
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(MARGEN, y, "Por la parte contratante:")
    c.drawString(ANCHO / 2, y, "Por la parte prestadora:")
    y -= 45
    c.line(MARGEN, y, MARGEN + 60 * mm, y)
    c.line(ANCHO / 2, y, ANCHO / 2 + 60 * mm, y)
    y -= 14
    c.setFont("Helvetica", 8)
    c.drawString(MARGEN, y, "Fdo.: (rúbrica sin identificar)")
    c.drawString(ANCHO / 2, y, "Fdo.: __________________")  # firma ausente
    linea(c, MARGEN, "Pág. 4")  # salto de numeración
    c.showPage()

    c.save()
    print(f"Generado: {SALIDA}  ({SALIDA.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
