"""Lectura y escritura de sitios.json (toda la configuración del programa)."""
import copy
import json
import os
import shutil
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
ARCHIVO = CARPETA / "sitios.json"          # variable de módulo: se puede cambiar para pruebas
EJEMPLO = CARPETA / "sitios.ejemplo.json"

OPCIONES_DEFECTO = {
    "usar_ia": False,
    "buscar_fotos": False,          # opción vieja; ahora manda modo_fotos
    "elegir_mejores": True,
    "licencia": "libre_primero",    # libre | libre_primero | cualquiera
    "modo_fotos": "internet_primero",   # internet_primero | cliente_e_internet | cliente | internet_si_faltan
    "migrado_internet_primero": True,
    "max_fotos": 4,
    "arreglar_fotos": True,
    "quitar_fondo": True,
    "max_zip_mb": 8,                # tamaño máximo de cada ZIP del paquete
}

_VACIO = {
    "openrouter_api_key": "",
    "openrouter_modelo": "openrouter/free",
    "gemini_api_key": "",
    "gemini_modelo": "gemini-3.5-flash-lite",
    "serpapi_key": "",
    "opciones": OPCIONES_DEFECTO,
    "sitios": [],
}


def vacio() -> dict:
    """Estructura por defecto, sin webs ni claves."""
    return copy.deepcopy(_VACIO)


def _completar(datos: dict) -> dict:
    base = vacio()
    opciones = dict(base["opciones"])
    guardadas = datos.get("opciones") or {}
    opciones.update(guardadas)
    if not guardadas.get("migrado_internet_primero"):
        # migración de una sola vez: el modo por defecto pasa a internet_primero
        opciones["modo_fotos"] = "internet_primero"
        opciones["migrado_internet_primero"] = True
    base.update(datos)
    base["opciones"] = opciones
    if not isinstance(base.get("sitios"), list):
        base["sitios"] = []
    for sitio in base["sitios"]:
        if isinstance(sitio, dict) and sitio.get("entrega") not in ("api", "paquete"):
            sitio["entrega"] = "api"
    return base


def cargar() -> dict:
    """Lee sitios.json. Si no existe lo crea desde el ejemplo, pero con sitios vacíos."""
    if not Path(ARCHIVO).exists():
        datos = vacio()
        try:
            with open(EJEMPLO, encoding="utf-8") as f:
                datos = _completar(json.load(f))
        except (OSError, ValueError):
            pass
        datos["sitios"] = []
        guardar(datos)
        return datos
    with open(ARCHIVO, encoding="utf-8") as f:
        return _completar(json.load(f))


def guardar(datos: dict) -> None:
    """Escribe a un archivo temporal y luego reemplaza el original."""
    destino = Path(ARCHIVO)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, destino)
