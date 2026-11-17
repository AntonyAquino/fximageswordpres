"""IA: nombre de producto por foto y búsqueda de fotos en internet."""
import base64
import io
import re
from pathlib import Path

import requests
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

PROMPT = ("Mirá la foto de este producto. Respondé solo con un nombre comercial corto para una "
          "tienda en línea en Guatemala (máximo 8 palabras): incluí marca y modelo si se ven, "
          "y el tipo de producto. Sin comillas ni explicaciones.")

UA_NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class ErrorIA(Exception):
    """Error de IA o de búsqueda de fotos, con mensaje en español."""


def _jpeg_bytes(ruta: Path, lado_max: int = 1024) -> bytes:
    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    img.thumbnail((lado_max, lado_max))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _limpiar(texto) -> str:
    if not texto:
        raise ErrorIA("La IA devolvió una respuesta vacía.")
    lineas = [l.strip() for l in str(texto).strip().splitlines() if l.strip()]
    if not lineas:
        raise ErrorIA("La IA devolvió una respuesta vacía.")
    t = lineas[0].strip(" \t\"'`“”‘’«»*")
    t = t[:80].strip()
    if not t:
        raise ErrorIA("La IA devolvió una respuesta vacía.")
    return t


def _openrouter(jpeg: bytes, config: dict) -> str:
    clave = config.get("openrouter_api_key", "")
    if not clave:
        raise ErrorIA("No hay clave de OpenRouter.")
    b64 = base64.b64encode(jpeg).decode()
    cuerpo = {
        "model": config.get("openrouter_modelo") or "openrouter/free",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "max_tokens": 600,
        "reasoning": {"enabled": False},
    }
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {clave}", "HTTP-Referer": "https://localhost",
                     "X-Title": "Subidor de productos"},
            json=cuerpo, timeout=60)
    except requests.exceptions.RequestException as e:
        raise ErrorIA(f"OpenRouter no respondió ({e.__class__.__name__}).")
    if r.status_code != 200:
        detalle = ""
        try:
            detalle = r.json().get("error", {}).get("message", "")
        except Exception:
            pass
        if r.status_code == 429:
            detalle = detalle or "límite de peticiones gratis alcanzado"
        raise ErrorIA(f"OpenRouter respondió con error HTTP {r.status_code}"
                      + (f": {detalle}" if detalle else "."))
    try:
        return _limpiar(r.json()["choices"][0]["message"]["content"])
    except ErrorIA:
        raise
    except Exception:
        raise ErrorIA("OpenRouter devolvió una respuesta inesperada.")


GEMINI_RESPALDO = "gemini-3.5-flash"


def _generar_gemini(clave: str, modelo: str, contents):
    """Llama a Gemini con tiempo límite de 60 s; si el modelo está saturado (503) o no
    existe (404), reintenta una vez con el modelo de respaldo."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=clave, http_options=types.HttpOptions(timeout=60000))
    try:
        return client.models.generate_content(model=modelo, contents=contents)
    except Exception as e:
        texto = str(e)
        if modelo != GEMINI_RESPALDO and ("503" in texto or "UNAVAILABLE" in texto
                                         or "404" in texto or "NOT_FOUND" in texto
                                         or "504" in texto or "DEADLINE" in texto):
            return client.models.generate_content(model=GEMINI_RESPALDO, contents=contents)
        raise


def _gemini(jpeg: bytes, config: dict) -> str:
    clave = config.get("gemini_api_key", "")
    if not clave:
        raise ErrorIA("No hay clave de Gemini.")
    try:
        from google import genai
        from google.genai import types
        resp = _generar_gemini(
            clave, config.get("gemini_modelo") or "gemini-3.5-flash-lite",
            [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), PROMPT])
        return _limpiar(resp.text)
    except ErrorIA:
        raise
    except Exception as e:
        raise ErrorIA(f"Gemini falló ({e.__class__.__name__}).")


def sugerir_nombre(ruta_foto, config: dict) -> tuple:
    """Devuelve (nombre, fuente) con fuente 'openrouter' o 'gemini'."""
    try:
        jpeg = _jpeg_bytes(Path(ruta_foto))
    except Exception:
        raise ErrorIA("No se pudo abrir la foto para sugerir el nombre.")
    errores = []
    if config.get("openrouter_api_key"):
        try:
            return _openrouter(jpeg, config), "openrouter"
        except ErrorIA as e:
            errores.append(str(e))
    if config.get("gemini_api_key"):
        try:
            return _gemini(jpeg, config), "gemini"
        except ErrorIA as e:
            errores.append(str(e))
    if not errores:
        errores.append("No hay claves de IA configuradas.")
    raise ErrorIA(" ".join(errores))


# ---------- pruebas de claves ----------
def probar_openrouter(clave: str) -> str:
    if not clave:
        raise ErrorIA("Escribí la clave primero.")
    try:
        r = requests.get("https://openrouter.ai/api/v1/auth/key",
                         headers={"Authorization": f"Bearer {clave}"}, timeout=20)
    except requests.exceptions.RequestException as e:
        raise ErrorIA(f"No se pudo conectar con OpenRouter ({e.__class__.__name__}).")
    if r.status_code in (401, 403):
        raise ErrorIA("OpenRouter no aceptó la clave (revisá que esté completa).")
    if r.status_code != 200:
        raise ErrorIA(f"OpenRouter respondió con error HTTP {r.status_code}.")
    try:
        d = r.json().get("data", {})
    except Exception:
        raise ErrorIA("OpenRouter devolvió una respuesta inesperada.")
    limite = d.get("limit")
    texto = (f"Clave válida · usado: {d.get('usage', 0)} · "
             f"límite: {limite if limite is not None else 'sin límite'}")
    if d.get("is_free_tier"):
        texto += " · cuenta gratis"
    return texto


def probar_gemini(clave: str, modelo: str = "") -> str:
    if not clave:
        raise ErrorIA("Escribí la clave primero.")
    modelo = modelo or "gemini-3.5-flash-lite"
    try:
        resp = _generar_gemini(clave, modelo, "Respondé solo: ok")
        respuesta = (resp.text or "").strip()
    except Exception as e:
        detalle = re.sub(r"[?&]key=[^&\s]+", "", str(e))[:160]
        raise ErrorIA(f"Gemini no respondió ({e.__class__.__name__}): {detalle}. "
                      "Revisá la clave y el nombre del modelo.")
    return f"Clave válida · modelo {modelo} respondió: {respuesta[:30] or '(vacío)'}"


def probar_serpapi(clave: str) -> str:
    if not clave:
        raise ErrorIA("Escribí la clave primero.")
    try:
        r = requests.get("https://serpapi.com/account.json", params={"api_key": clave}, timeout=20)
    except requests.exceptions.RequestException as e:
        raise ErrorIA(f"No se pudo conectar con SerpAPI ({e.__class__.__name__}).")
    if r.status_code in (401, 403):
        raise ErrorIA("SerpAPI no aceptó la clave.")
    if r.status_code != 200:
        raise ErrorIA(f"SerpAPI respondió con error HTTP {r.status_code}.")
    try:
        d = r.json()
    except Exception:
        raise ErrorIA("SerpAPI devolvió una respuesta inesperada.")
    return f"Clave válida · búsquedas que quedan este mes: {d.get('plan_searches_left', '?')}"


# ---------- búsqueda de fotos ----------
LICENCIA_DDGS = "ShareCommercially"   # ddgs: license_image (uso y distribución comercial)
LICENCIA_SERPAPI = "fc"                # SerpAPI google_images: licenses=fc (libre, incluso comercial)

NOTA_LIBRE_SIN = "no se encontraron fotos de libre uso"
NOTA_LIBRE_OK = "fotos de internet con filtro de libre uso (no es garantía legal)"
NOTA_PRIMERO_SIN = "fotos sin licencia confirmada, reemplazar por fotos del cliente"
NOTA_CUALQUIERA = "fotos de internet, revisar derechos de autor"


def _urls_ddgs(nombre: str, licencia: bool = False) -> list:
    from ddgs import DDGS
    extra = {"license_image": LICENCIA_DDGS} if licencia else {}
    res = DDGS().images(nombre, max_results=20, **extra)
    return [r.get("image") for r in res if r.get("image")]


def _urls_serpapi(nombre: str, clave: str, licencia: bool = False) -> list:
    params = {"engine": "google_images", "q": nombre, "api_key": clave}
    if licencia:
        params["licenses"] = LICENCIA_SERPAPI
    r = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    r.raise_for_status()
    return [x.get("original") for x in r.json().get("images_results", [])[:20] if x.get("original")]


def _hash_perceptual(img: Image.Image) -> int:
    """Imagen a 8x8 en gris; cada bit dice si el pixel supera el promedio."""
    g = img.convert("L").resize((8, 8))
    px = list(g.getdata())
    prom = sum(px) / len(px)
    h = 0
    for p in px:
        h = (h << 1) | (1 if p > prom else 0)
    return h


def _distancia(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _evaluar(contenido: bytes, url: str = "", lado_minimo: int = 600):
    """Abre la imagen y devuelve un dict, o None si se descarta (GIF, chica o ilegible)."""
    try:
        img = Image.open(io.BytesIO(contenido))
        formato = (img.format or "").upper()
        if formato == "GIF":
            return None
        img = ImageOps.exif_transpose(img)
        ancho, alto = img.size
        if min(ancho, alto) < lado_minimo:
            return None
        return {"url": url, "bytes": contenido, "formato": formato, "ancho": ancho,
                "alto": alto, "area": ancho * alto, "hash": _hash_perceptual(img),
                "img": img.convert("RGB")}
    except Exception:
        return None


def _sin_repetidas(candidatas: list, umbral: int = 4) -> list:
    unicas = []
    for c in candidatas:
        if all(_distancia(c["hash"], u["hash"]) > umbral for u in unicas):
            unicas.append(c)
    return unicas


def _ordenar(candidatas: list) -> list:
    """Mayor área primero, pero las de proporción razonable (0.6 a 1.7) van antes."""
    def clave(c):
        prop = c["ancho"] / c["alto"]
        return (0 if 0.6 <= prop <= 1.7 else 1, -c["area"])
    return sorted(candidatas, key=clave)


def _miniatura(c: dict) -> bytes:
    im = c["img"].copy()
    im.thumbnail((512, 512))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _pedido_elegir(nombre: str, maximo: int, n_cliente: int = 0, total: int = 0,
                   modo: str = "cliente_e_internet") -> str:
    base = f"Producto de una tienda en línea: «{nombre}». "
    if n_cliente > 0:
        if total > n_cliente:
            if modo == "internet_primero":
                origen = (f"Las fotos 1 a {n_cliente} son del cliente, tomadas en vitrina; "
                          f"preferí las de internet ({n_cliente + 1} a {total}) si son del "
                          "producto exacto; elegí una del cliente solo si no hay ninguna buena "
                          "de internet o si el producto es artesanal o sin marca. ")
            else:
                origen = (f"Las fotos 1 a {n_cliente} son del cliente (ya retocadas) y las fotos "
                          f"{n_cliente + 1} a {total} vienen de internet. ")
        else:
            origen = f"Todas las fotos (1 a {total}) son del cliente (ya retocadas). "
    else:
        origen = "Todas las fotos vienen de internet. "
    reglas = ("Elegí las que muestren claramente ese producto exacto (no uno parecido), con buena "
              "calidad. Descartá las fotos con marca de agua, logos o nombres de tiendas, texto "
              "superpuesto, precios, collages, varias unidades distintas, un producto distinto o "
              "otra presentación (otro tamaño o variante) cuando se note. Preferí una sola unidad "
              "del producto exacto, fondo blanco o neutro, bien iluminada y nítida. ")
    if modo != "internet_primero" and n_cliente > 0:
        reglas += ("Si una foto del cliente es aceptable, mantenela en vez de cambiarla por una "
                   "de internet. ")
    return (base + origen + reglas +
            f"Si dudás de que una foto sea exactamente ese producto y presentación, no la incluyas: es mejor 1 foto correcta que 3 con una equivocada. Respondé solo con los números de las mejores, hasta {maximo}, separados por coma, "
            "de mejor a peor. Si ninguna sirve respondé 0. Respondé solo con los números.")


def _parsear_numeros(texto: str, cantidad: int, maximo: int) -> list:
    nums = []
    for m in re.findall(r"\d+", texto or ""):
        n = int(m)
        if n == 0 and not nums:
            return []
        if 1 <= n <= cantidad and n not in nums:
            nums.append(n)
    return nums[:maximo]


def _elegir_openrouter(minis: list, pedido: str, config: dict) -> str:
    clave = config.get("openrouter_api_key", "")
    contenido = [{"type": "text", "text": pedido}]
    for i, m in enumerate(minis, 1):
        b64 = base64.b64encode(m).decode()
        contenido.append({"type": "text", "text": f"Foto {i}:"})
        contenido.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {clave}", "HTTP-Referer": "https://localhost",
                     "X-Title": "Subidor de productos"},
            json={"model": config.get("openrouter_modelo") or "openrouter/free",
                  "messages": [{"role": "user", "content": contenido}], "max_tokens": 300,
                  "reasoning": {"enabled": False}},
            timeout=90)
    except requests.exceptions.RequestException as e:
        raise ErrorIA(f"OpenRouter no respondió ({e.__class__.__name__}).")
    if r.status_code != 200:
        raise ErrorIA(f"OpenRouter respondió con error HTTP {r.status_code}.")
    try:
        return str(r.json()["choices"][0]["message"]["content"] or "")
    except Exception:
        raise ErrorIA("OpenRouter devolvió una respuesta inesperada.")


def _elegir_gemini(minis: list, pedido: str, config: dict) -> str:
    try:
        from google import genai
        from google.genai import types
        partes = []
        for i, m in enumerate(minis, 1):
            partes.append(f"Foto {i}:")
            partes.append(types.Part.from_bytes(data=m, mime_type="image/jpeg"))
        partes.append(pedido)
        resp = _generar_gemini(config.get("gemini_api_key", ""),
                               config.get("gemini_modelo") or "gemini-3.5-flash-lite", partes)
        return resp.text or ""
    except Exception as e:
        raise ErrorIA(f"Gemini falló ({e.__class__.__name__}).")


def elegir_con_ia(items: list, nombre: str, maximo: int, config: dict, log,
                  n_cliente: int = 0, modo: str = "cliente_e_internet") -> list:
    """items: dicts con 'img' (PIL RGB), del cliente primero y luego internet.
    Devuelve los items elegidos por la IA (vacío si no pudo o ninguna sirve)."""
    lote = items[:8]
    n_cliente = min(n_cliente, len(lote))
    minis = [_miniatura(c) for c in lote]
    pedido = _pedido_elegir(nombre, maximo, n_cliente, len(lote), modo)
    proveedores = []
    if config.get("openrouter_api_key"):
        proveedores.append(("OpenRouter", _elegir_openrouter))
    if config.get("gemini_api_key"):
        proveedores.append(("Gemini", _elegir_gemini))
    for etiqueta, fn in proveedores:
        try:
            nums = _parsear_numeros(fn(minis, pedido, config), len(lote), maximo)
        except ErrorIA as e:
            log(f"{etiqueta}: {e}")
            continue
        if nums:
            return [lote[n - 1] for n in nums]
        log(f"{etiqueta} no eligió ninguna foto.")
    return []


def guardar_foto(c: dict, carpeta: Path, slug: str, n: int) -> Path:
    """Guarda la foto de internet en carpeta y la anota en fuentes.txt."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    if c["formato"] == "PNG":
        ruta = carpeta / f"{slug}-{n}.png"
        ruta.write_bytes(c["bytes"])
    elif c["formato"] == "JPEG":
        ruta = carpeta / f"{slug}-{n}.jpg"
        ruta.write_bytes(c["bytes"])
    else:
        ruta = carpeta / f"{slug}-{n}.jpg"
        c["img"].save(ruta, "JPEG", quality=90)
    try:
        fuentes = carpeta / "fuentes.txt"
        previas = []
        if fuentes.exists():  # si el archivo se sobrescribe, se reemplaza su línea
            previas = [l for l in fuentes.read_text(encoding="utf-8").splitlines()
                       if not l.startswith(ruta.name + " | ")]
        with open(fuentes, "w", encoding="utf-8") as f:
            f.write("".join(l + "\n" for l in previas))
            f.write(f"{ruta.name} | {c.get('url', '')} | "
                    f"{'sí' if c.get('filtrada') else 'no'}\n")
    except OSError:
        pass
    return ruta


SOSPECHOSAS = ("watermark", "marca-de-agua", "stock", "shutterstock", "alamy", "dreamstime",
               "123rf", "istock", "depositphotos", "gettyimages")


def _url_sospechosa(url: str) -> bool:
    """True si la URL (dominio o nombre de archivo) sugiere foto de stock con marca de agua."""
    u = (url or "").lower()
    return any(s in u for s in SOSPECHOSAS)


def _descargar(urls: list, filtrada: bool, limite: int = 12) -> list:
    vistas, unicas = set(), []
    for u in urls:
        if _url_sospechosa(u):
            continue
        if u not in vistas:
            vistas.add(u)
            unicas.append(u)
    candidatas = []
    for url in unicas:
        if len(candidatas) >= limite:
            break
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": UA_NAVEGADOR})
            r.raise_for_status()
        except Exception:
            continue
        c = _evaluar(r.content, url)
        if c:
            c["filtrada"] = filtrada
            candidatas.append(c)
    return _ordenar(_sin_repetidas(candidatas))


def _buscar_urls(nombre: str, config: dict, licencia: bool, log) -> list:
    urls = []
    try:
        urls += _urls_ddgs(nombre, licencia=licencia)
    except Exception as e:
        log(f"DuckDuckGo no respondió ({e.__class__.__name__}).")
    if config.get("serpapi_key"):
        try:
            urls += _urls_serpapi(nombre, config["serpapi_key"], licencia=licencia)
        except Exception as e:
            log(f"SerpAPI no respondió ({e.__class__.__name__}).")
    return urls


def buscar_candidatas(nombre: str, config: dict, licencia: str = "libre_primero",
                      log=None) -> tuple:
    """Busca y descarga candidatas según el modo de licencia.
    Devuelve (candidatas ordenadas, nota). Cada candidata trae 'filtrada' True/False."""
    log = log or (lambda m: None)
    if licencia not in ("libre", "libre_primero", "cualquiera"):
        licencia = "libre_primero"
    if licencia == "cualquiera":
        c = _descargar(_buscar_urls(nombre, config, False, log), False)
        return c, (NOTA_CUALQUIERA if c else "")
    c = _descargar(_buscar_urls(nombre, config, True, log), True)
    if c:
        return c, NOTA_LIBRE_OK
    if licencia == "libre":
        return [], NOTA_LIBRE_SIN
    log("Sin fotos de libre uso; se busca sin filtro de licencia.")
    c = _descargar(_buscar_urls(nombre, config, False, log), False)
    return c, (NOTA_PRIMERO_SIN if c else "")
