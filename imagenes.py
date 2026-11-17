"""Conversión de fotos a WebP (y JPG como respaldo)."""
import logging
import re
import time
import unicodedata
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger("subidor")

try:  # HEIC/HEIF de iPhone, si está instalado pillow-heif
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass


def nombre_ascii(texto: str) -> str:
    """Convierte un texto a slug ASCII: sin tildes, minúsculas y con guiones."""
    t = unicodedata.normalize("NFKD", str(texto))
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "imagen"


def _destino_libre(destino_dir: Path, base: str, ext: str) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    ruta = destino_dir / f"{base}{ext}"
    n = 2
    while ruta.exists():
        ruta = destino_dir / f"{base}-{n}{ext}"
        n += 1
    return ruta


def _abrir(origen: Path, lado_max: int, con_alfa: bool) -> Image.Image:
    img = Image.open(origen)
    img = ImageOps.exif_transpose(img)
    tiene_alfa = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    if con_alfa and tiene_alfa:
        img = img.convert("RGBA")
    elif tiene_alfa:  # JPG no admite transparencia: fondo blanco
        rgba = img.convert("RGBA")
        fondo = Image.new("RGB", rgba.size, (255, 255, 255))
        fondo.paste(rgba, mask=rgba.split()[3])
        img = fondo
    else:
        img = img.convert("RGB")
    img.thumbnail((lado_max, lado_max))
    return img


def guardar_webp(img: Image.Image, destino_dir: Path, nombre: str, lado_max: int = 1600,
                 calidad: int = 82) -> Path:
    """Guarda una imagen PIL como WebP en destino_dir con nombre ASCII sin repetir."""
    img = img.copy()
    img.thumbnail((lado_max, lado_max))
    destino = _destino_libre(Path(destino_dir), nombre_ascii(nombre), ".webp")
    img.save(destino, "WEBP", quality=calidad, method=6)
    return destino


def convertir_a_webp(origen: Path, destino_dir: Path, lado_max: int = 1600,
                     calidad: int = 82) -> Path:
    origen = Path(origen)
    img = _abrir(origen, lado_max, con_alfa=True)
    return guardar_webp(img, destino_dir, origen.stem, lado_max, calidad)


# ---------- arreglo automático ----------
def abrir_rgb(origen: Path) -> Image.Image:
    """Abre una foto (con EXIF aplicado) como RGB; la transparencia queda sobre blanco."""
    return _abrir(Path(origen), 4000, con_alfa=False)


def _luminancia(img: Image.Image) -> float:
    g = img.convert("L").resize((64, 64))
    px = list(g.getdata())
    return sum(px) / len(px)


def _balance_blancos(img: Image.Image) -> Image.Image:
    """Escala cada canal para que el promedio del 5% más claro sea neutro (tope 1.3)."""
    chico = img.resize((128, 128))
    px = list(chico.getdata())
    px.sort(key=lambda p: p[0] + p[1] + p[2])
    top = px[-max(1, len(px) // 20):]
    medias = [sum(p[i] for p in top) / len(top) for i in range(3)]
    gris = sum(medias) / 3
    if gris < 1:
        return img
    factores = [min(1.3, max(1 / 1.3, gris / m)) if m > 1 else 1.0 for m in medias]
    canales = [c.point(lambda v, f=f: min(255, int(v * f + 0.5)))
               for c, f in zip(img.split(), factores)]
    return Image.merge("RGB", canales)


def arreglar(img: Image.Image) -> Image.Image:
    """Mejora una foto mala: orientación, contraste, balance de blancos, nitidez y brillo."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = _balance_blancos(img)
    img = ImageEnhance.Sharpness(img).enhance(1.3)
    lum = _luminancia(img)
    if lum < 90:
        img = ImageEnhance.Brightness(img).enhance(min(1.25, 90 / max(lum, 1)))
    return img


# ---------- quitar fondo ----------
_sesion = None
_sesion_error = None


def quitador_disponible() -> bool:
    """True si rembg se puede importar."""
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


def _obtener_sesion():
    global _sesion, _sesion_error
    if _sesion is None:
        from rembg import new_session
        _sesion = new_session("u2net")
    return _sesion


def quitar_fondo(img: Image.Image) -> Image.Image:
    """Recorta el objeto y lo pone sobre lienzo blanco cuadrado (margen 8%). Lanza excepción si falla."""
    from rembg import remove
    t0 = time.time()
    img = img.convert("RGB")
    rgba = remove(img, session=_obtener_sesion()).convert("RGBA")
    caja = rgba.split()[3].point(lambda v: 255 if v > 10 else 0).getbbox()
    if not caja:
        raise RuntimeError("no se detectó ningún objeto")
    recorte = rgba.crop(caja)
    margen = int(max(recorte.size) * 0.08)
    lado = max(recorte.size) + 2 * margen
    lienzo = Image.new("RGB", (lado, lado), (255, 255, 255))
    x = (lado - recorte.width) // 2
    y = (lado - recorte.height) // 2
    lienzo.paste(recorte, (x, y), recorte.split()[3])
    lienzo.thumbnail((1600, 1600))
    logger.info("quitar_fondo: %.1f s", time.time() - t0)
    return lienzo


def convertir_a_jpg(origen: Path, destino_dir: Path, lado_max: int = 1600,
                    calidad: int = 85) -> Path:
    origen = Path(origen)
    img = _abrir(origen, lado_max, con_alfa=False)
    destino = _destino_libre(Path(destino_dir), nombre_ascii(origen.stem), ".jpg")
    img.save(destino, "JPEG", quality=calidad, optimize=True)
    return destino
