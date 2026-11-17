"""Crea plugin/subidor-productos.zip a partir de plugin/subidor-productos/ (para instalarlo en WordPress)."""
import zipfile
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
ORIGEN = CARPETA / "plugin" / "subidor-productos"
DESTINO = CARPETA / "plugin" / "subidor-productos.zip"


def empaquetar() -> Path:
    if not ORIGEN.is_dir():
        raise FileNotFoundError(f"No existe {ORIGEN}")
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ORIGEN.rglob("*")):
            if f.is_file():
                # WordPress espera la carpeta del plugin dentro del ZIP
                z.write(f, f"subidor-productos/{f.relative_to(ORIGEN).as_posix()}")
    return DESTINO


if __name__ == "__main__":
    ruta = empaquetar()
    print(f"Listo: {ruta} ({ruta.stat().st_size} bytes)")
