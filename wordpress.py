"""Clientes REST de WordPress y WooCommerce."""
import mimetypes
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

UA = "SubidorDeProductos/1.0"
TIMEOUT = 60

TIPOS_EXCLUIDOS = {
    "attachment", "wp_block", "wp_template", "wp_navigation", "nav_menu_item",
    "wp_template_part", "wp_global_styles", "wp_font_family", "wp_font_face",
}


class ErrorWeb(Exception):
    """Error de comunicación con el sitio, con mensaje en español."""


class TipoNoPermitido(ErrorWeb):
    """El servidor rechazó el tipo de archivo (por ejemplo WebP)."""


def _mensaje_wp(resp) -> str:
    try:
        datos = resp.json()
        if isinstance(datos, dict) and datos.get("message"):
            return str(datos["message"])
    except Exception:
        pass
    return ""


def _error_http(resp, accion: str) -> ErrorWeb:
    msg = _mensaje_wp(resp)
    pistas = {
        401: "Usuario o contraseña incorrectos.",
        403: "Sin permiso (revisá el rol del usuario o la seguridad del hosting).",
        404: "No se encontró la dirección (revisá la URL o el post type).",
    }
    texto = f"Error HTTP {resp.status_code} al {accion}"
    if msg:
        texto += f": {msg}"
    elif resp.status_code in pistas:
        texto += f": {pistas[resp.status_code]}"
    return ErrorWeb(texto)


def _pedir(sesion, metodo, url, accion, **kw):
    try:
        return sesion.request(metodo, url, timeout=TIMEOUT, **kw)
    except requests.exceptions.SSLError:
        raise ErrorWeb(f"Error de certificado SSL al {accion}.")
    except requests.exceptions.ConnectionError:
        raise ErrorWeb(f"No se pudo conectar con el sitio al {accion}. Revisá la URL y el internet.")
    except requests.exceptions.Timeout:
        raise ErrorWeb(f"El sitio tardó demasiado en responder al {accion}.")
    except requests.exceptions.RequestException as e:
        raise ErrorWeb(f"Fallo de red al {accion}: {e.__class__.__name__}")


def normalizar_url(url: str) -> str:
    """Deja solo la dirección principal del sitio (sin /wp-admin, /wp-json, etc.)."""
    u = (url or "").strip()
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    p = urlsplit(u)
    ruta = p.path
    patrones = [r"/wp-admin(/.*)?$", r"/wp-login\.php$", r"/wp-json(/.*)?$",
                r"/index\.php$", r"/xmlrpc\.php$", r"/+$"]
    cambio = True
    while cambio:
        cambio = False
        for pat in patrones:
            nueva = re.sub(pat, "", ruta, flags=re.I)
            if nueva != ruta:
                ruta, cambio = nueva, True
    return urlunsplit((p.scheme, p.netloc, ruta, "", ""))


def _titulo_html(cuerpo: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", cuerpo or "", re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


MARCA_HOSTING = "bloquea cualquier programa que no sea un navegador"


def diagnosticar_html(resp) -> str:
    """Explica en español por qué el sitio devolvió HTML en vez de la API."""
    cuerpo = resp.text or ""
    bajo = cuerpo.lower()
    h = {k.lower(): v for k, v in resp.headers.items()}
    titulo = _titulo_html(cuerpo)
    codigo = resp.status_code
    if ("aes.js" in bajo or "__test" in bajo
            or (h.get("server", "").lower() == "openresty" and "<html" in bajo and not titulo)):
        msg = ("Este hosting (InfinityFree u otro gratuito con protección anti-robots) " + MARCA_HOSTING +
               ", así que la API de WordPress no se puede usar desde esta app. Opciones: mover la "
               "web a un hosting que permita la API, o subir estos productos a mano.")
    elif h.get("cf-mitigated", "").lower() == "challenge" or "just a moment" in bajo or "cf-challenge" in bajo:
        msg = ("Cloudflare está pidiendo verificación de navegador. Hay que crear una regla en "
               "Cloudflare que permita la ruta /wp-json/.")
    else:
        msg = ""
        if codigo == 403:
            for nombre in ("Wordfence", "iThemes", "Solid Security", "ModSecurity", "Sucuri"):
                if nombre.lower() in bajo:
                    msg = (f"Un plugin o módulo de seguridad bloqueó la petición ({nombre}). Hay que "
                           "permitir la REST API o la IP de esta computadora.")
                    break
        if not msg and any(x in bajo for x in ("coming soon", "próximamente", "proximamente", "maintenance",
                                               "mantenimiento", "seedprod", "under construction")):
            msg = ("La web tiene activada una página de 'próximamente' o mantenimiento que también "
                   "tapa la API. Desactivala o excluí /wp-json/.")
        if not msg and codigo == 404:
            msg = ("No existe la ruta de la API. Revisá la URL (debe ser la raíz de la web) y que "
                   "los enlaces permanentes no estén en modo simple.")
        if not msg:
            msg = (f"El sitio devolvió una página HTML en vez de la API (HTTP {codigo}, título: "
                   f"{titulo or 'sin título'}). Revisá la URL y si algún plugin bloquea la REST API.")
    return f"{msg} (URL que respondió: {resp.url})"


def _es_html_o_no_json(resp) -> bool:
    try:
        resp.json()
        return False
    except Exception:
        return True


def _json(resp, accion):
    try:
        return resp.json()
    except Exception:
        raise ErrorWeb(diagnosticar_html(resp))


def _sin_tildes(t: str) -> str:
    n = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in n if not unicodedata.combining(c)).casefold().strip()



def _construir_api(base: str, modo: str, ruta: str) -> str:
    ruta = ruta.lstrip("/")
    if modo == "rest_route":
        path, _, query = ruta.partition("?")
        url = f"{base}/?rest_route=/{path}"
        return url + (f"&{query}" if query else "")
    return f"{base}/wp-json/{ruta}"


class ClienteWP:
    def __init__(self, url: str, usuario: str, app_password: str, modo_rest: str = "wp-json"):
        self.url = normalizar_url(url)
        self.modo_rest = modo_rest
        self.s = requests.Session()
        self.s.auth = (usuario, app_password)
        self.s.headers.update({"User-Agent": UA})

    def _api(self, ruta: str) -> str:
        return _construir_api(self.url, self.modo_rest, ruta)

    def probar(self) -> dict:
        accion = "probar la conexión"
        ruta = "wp/v2/users/me?context=edit"
        r = _pedir(self.s, "GET", self._api(ruta), accion)
        if self.modo_rest == "wp-json" and (r.status_code == 404 or _es_html_o_no_json(r)):
            self.modo_rest = "rest_route"
            r2 = _pedir(self.s, "GET", self._api(ruta), accion)
            if r2.status_code == 200 and not _es_html_o_no_json(r2):
                r = r2
            else:
                self.modo_rest = "wp-json"
        if r.status_code != 200:
            if _es_html_o_no_json(r):
                raise ErrorWeb(diagnosticar_html(r))
            raise _error_http(r, accion)
        d = _json(r, accion)
        return {"nombre": d.get("name", ""), "roles": d.get("roles", []),
                "modo_rest": self.modo_rest}

    def tipos_contenido(self) -> list:
        r = _pedir(self.s, "GET", self._api("wp/v2/types?context=edit"), "leer los tipos de contenido")
        if r.status_code != 200:
            r = _pedir(self.s, "GET", self._api("wp/v2/types"), "leer los tipos de contenido")
        if r.status_code != 200:
            raise _error_http(r, "leer los tipos de contenido")
        d = _json(r, "leer los tipos de contenido")
        salida = []
        for slug, t in d.items():
            if slug in TIPOS_EXCLUIDOS:
                continue
            salida.append({"slug": slug, "nombre": t.get("name", slug),
                           "rest_base": t.get("rest_base") or slug})
        return salida

    def subir_medio(self, ruta, titulo: str, alt: str) -> dict:
        ruta = Path(ruta)
        mime = mimetypes.guess_type(ruta.name)[0]
        if ruta.suffix.lower() == ".webp":
            mime = "image/webp"
        mime = mime or "application/octet-stream"
        with open(ruta, "rb") as fh:
            r = _pedir(self.s, "POST", self._api("wp/v2/media"), "subir la imagen",
                       files={"file": (ruta.name, fh, mime)},
                       data={"title": titulo, "alt_text": alt})
        if r.status_code not in (200, 201):
            msg = _mensaje_wp(r).lower()
            tipo_malo = any(p in msg for p in ("tipo de archivo", "file type", "not allowed",
                                               "no está permitido", "mime"))
            if r.status_code == 415 or (r.status_code in (500, 400) and tipo_malo):
                raise TipoNoPermitido(f"El sitio no acepta este tipo de archivo ({ruta.suffix}).")
            raise _error_http(r, "subir la imagen")
        d = _json(r, "subir la imagen")
        if (d.get("alt_text") or "") != alt:
            _pedir(self.s, "POST", self._api(f"wp/v2/media/{d['id']}"), "ajustar el texto alternativo",
                   json={"title": titulo, "alt_text": alt})
        return {"id": d["id"], "url": d.get("source_url", "")}

    def crear_entrada(self, rest_base: str, titulo: str, featured_media: int,
                      content: str, status: str = "draft") -> dict:
        cuerpo = {"title": titulo, "status": status, "content": content}
        if featured_media:
            cuerpo["featured_media"] = featured_media
        r = _pedir(self.s, "POST", self._api(f"wp/v2/{rest_base}"), "crear la entrada", json=cuerpo)
        if r.status_code not in (200, 201):
            raise _error_http(r, "crear la entrada")
        d = _json(r, "crear la entrada")
        return {"id": d["id"], "link": d.get("link", "")}


class ClienteWoo:
    def __init__(self, url: str, key: str, secret: str, modo_rest: str = "wp-json"):
        self.url = normalizar_url(url)
        self.modo_rest = modo_rest
        self.s = requests.Session()
        self.s.auth = (key, secret)
        self.s.headers.update({"User-Agent": UA})

    def _api(self, ruta: str) -> str:
        return _construir_api(self.url, self.modo_rest, "wc/v3/" + ruta.lstrip("/"))

    def probar(self) -> bool:
        accion = "probar WooCommerce"
        r = _pedir(self.s, "GET", self._api("products?per_page=1"), accion)
        if self.modo_rest == "wp-json" and (r.status_code == 404 or _es_html_o_no_json(r)):
            self.modo_rest = "rest_route"
            r2 = _pedir(self.s, "GET", self._api("products?per_page=1"), accion)
            if r2.status_code == 200 and not _es_html_o_no_json(r2):
                r = r2
            else:
                self.modo_rest = "wp-json"
        if r.status_code != 200:
            if _es_html_o_no_json(r):
                raise ErrorWeb(diagnosticar_html(r))
            raise _error_http(r, accion)
        return True

    def categoria_id(self, nombre: str) -> int:
        r = _pedir(self.s, "GET", self._api("products/categories"), "buscar la categoría",
                   params={"search": nombre, "per_page": 100})
        if r.status_code != 200:
            raise _error_http(r, "buscar la categoría")
        buscado = _sin_tildes(nombre)
        for c in _json(r, "buscar la categoría"):
            if _sin_tildes(c.get("name", "")) == buscado:
                return c["id"]
        r = _pedir(self.s, "POST", self._api("products/categories"), "crear la categoría",
                   json={"name": nombre})
        if r.status_code not in (200, 201):
            raise _error_http(r, "crear la categoría")
        return _json(r, "crear la categoría")["id"]

    def crear_producto(self, nombre, ids_imagenes, descripcion=None, precio=None,
                       categoria_id=None) -> dict:
        cuerpo = {"name": nombre, "type": "simple", "status": "draft",
                  "images": [{"id": i} for i in ids_imagenes]}
        if precio not in (None, ""):
            cuerpo["regular_price"] = str(precio)
        if descripcion:
            cuerpo["description"] = descripcion
        if categoria_id:
            cuerpo["categories"] = [{"id": categoria_id}]
        r = _pedir(self.s, "POST", self._api("products"), "crear el producto", json=cuerpo)
        if r.status_code not in (200, 201):
            raise _error_http(r, "crear el producto")
        d = _json(r, "crear el producto")
        return {"id": d["id"], "permalink": d.get("permalink", "")}
