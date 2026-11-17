"""Genera plantilla.xlsx con las columnas que usa el Subidor de productos."""
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

CARPETA = Path(__file__).resolve().parent
COLUMNAS = ["nombre", "fotos", "categoria", "descripcion", "precio",
            "estado", "id", "enlace_edicion", "nota"]
EJEMPLOS = [
    ["Zapatos deportivos Nike Air", "nike1.jpg; nike2.jpg", "Calzado",
     "Zapatos cómodos para correr", 450, "", "", "", ""],
    ["", "foto-sin-nombre.jpg", "", "", "", "", "", "", ""],
]


def crear(destino: Path = CARPETA / "plantilla.xlsx") -> Path:
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "productos"
    hoja.append(COLUMNAS)
    for f in EJEMPLOS:
        hoja.append(f)
    for c in range(1, len(COLUMNAS) + 1):
        celda = hoja.cell(row=1, column=c)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F4E78" if c <= 5 else "7F7F7F")
        hoja.column_dimensions[get_column_letter(c)].width = 28 if c in (1, 2, 4, 8, 9) else 16
    hoja.freeze_panes = "A2"
    wb.save(destino)
    return destino


if __name__ == "__main__":
    print("Plantilla creada en", crear())
