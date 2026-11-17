"""Núcleo del proceso: lee productos.xlsx, convierte fotos, sube y crea borradores."""
import csv
import hashlib
import io
import logging
import time
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl
from PIL import Image

import config as cfg
import ia
import imagenes
from wordpress import ClienteWP, ClienteWoo, ErrorWeb, TipoNoPermitido

CARPETA_PROGRAMA = Path(__file__).resolve().parent
ARCHIVO_LOG = CARPETA_PROGRAMA / "registro.log"

COLS_ENTRADA = ["nombre", "fotos", "categoria", "descripcion", "precio"]
COLS_SALIDA = ["estado", "id", "enlace_edicion", "nota"]

EXT_FOTOS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
COLS_HOJA_NUEVA = ["nombre", "fotos", "categoria", "descripcion", "precio",
                   "estado", "id", "enlace_edicion", "nota"]

logger = logging.getLogger("subidor")


def listar_fotos(carpeta) -> list:
    """Fotos que están directamente en la carpeta (no en subcarpetas), ordenadas por nombre."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    fotos = [p for p in carpeta.iterdir()
             if p.is_file() and p.suffix.lower() in EXT_FOTOS
             and not p.name.startswith(("~$", "."))]
    return sorted(fotos, key=lambda p: p.name.casefold())


def crear_hoja_desde_fotos(carpeta) -> tuple:
    """Crea productos.xlsx con una fila por foto. No pisa una hoja existente."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    carpeta = Path(carpeta)
    destino = carpeta / "productos.xlsx"
    if destino.exists():
        raise FileExistsError(f"Ya existe {destino}")
    fotos = listar_fotos(carpeta)
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "productos"
    hoja.append(COLS_HOJA_NUEVA)
    for c in range(1, len(COLS_HOJA_NUEVA) + 1):
        hoja.cell(row=1, column=c).font = Font(bold=True)
    for f in fotos:
        hoja.append(["", f.name])
    anchos = [32, 48, 18, 40, 10, 14, 8, 40, 40]
    for i, a in enumerate(anchos, 1):
        hoja.column_dimensions[get_column_letter(i)].width = a
    hoja.freeze_panes = "A2"
    wb.save(destino)
    return destino, len(fotos)


def _preparar_log():
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        h = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
    except OSError:
        logger.addHandler(logging.NullHandler())


def norm(texto) -> str:
    """Minúsculas y sin tildes, para comparar encabezados."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).casefold().strip()


def mapear_columnas(hoja) -> dict:
    """Devuelve {nombre_normalizado: numero_columna}; crea al final las de salida que falten."""
    mapa = {}
    for c in range(1, hoja.max_column + 1):
        v = hoja.cell(row=1, column=c).value
        if v is not None and norm(v):
            mapa.setdefault(norm(v), c)
    if "nombre" not in mapa and "fotos" not in mapa:
        raise ValueError("La hoja necesita al menos la columna 'nombre' o la columna 'fotos' "
                         "en la fila 1.")
    ultima = max(mapa.values()) if mapa else 0
    for col in COLS_SALIDA:
        if col not in mapa:
            ultima += 1
            hoja.cell(row=1, column=ultima, value=col)
            mapa[col] = ultima
    return mapa


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _guardar(wb, ruta_xlsx: Path, carpeta: Path, log) -> Path:
    try:
        wb.save(ruta_xlsx)
        return ruta_xlsx
    except PermissionError:
        copia = carpeta / "productos_resultado.xlsx"
        log("AVISO: productos.xlsx está abierto en Excel y no se pudo guardar. "
            "Cierrelo. Se guarda una copia en productos_resultado.xlsx.")
        wb.save(copia)
        return copia


def _bloques_imagen(imgs: list, nombre: str) -> str:
    return "\n".join(
        '<!-- wp:image {"id":%d,"sizeSlug":"large"} --><figure class="wp-block-image size-large">'
        '<img src="%s" alt="%s" class="wp-image-%d"/></figure><!-- /wp:image -->'
        % (i["id"], i["url"], nombre.replace('"', "&quot;"), i["id"]) for i in imgs)


def _separar_fotos(texto: str) -> list:
    return [p.strip() for p in texto.replace(",", ";").split(";") if p.strip()]


def filas_a_procesar(hoja, cols) -> list:
    """Números de fila con datos y sin estado 'subido'."""
    filas = []
    for fila in range(2, hoja.max_row + 1):
        if all(_texto(hoja.cell(row=fila, column=c).value) == "" for c in range(1, hoja.max_column + 1)):
            continue
        if "estado" in cols and norm(hoja.cell(row=fila, column=cols["estado"]).value) in (
                "subido", "empaquetado"):
            continue
        filas.append(fila)
    return filas


def _preparar_cliente(ruta: Path, opc: dict, notas: list) -> "Image.Image":
    """Abre una foto del cliente y le aplica arreglar / quitar fondo según las opciones."""
    img = imagenes.abrir_rgb(ruta)
    if opc.get("arreglar_fotos"):
        img = imagenes.arreglar(img)
    if opc.get("quitar_fondo"):
        t0 = time.time()
        try:
            img = imagenes.quitar_fondo(img)
            logger.info("Fondo quitado de %s en %.1f s", ruta.name, time.time() - t0)
        except Exception as e:
            logger.info("No se pudo quitar el fondo de %s (%s: %s)", ruta.name,
                        e.__class__.__name__, e)
            if "no se pudo quitar el fondo" not in notas:
                notas.append("no se pudo quitar el fondo")
    return img


def _elegir_fotos(nombre, cliente, internet, maximo, usar_elegir, config, avisar,
                  modo: str = "cliente_e_internet") -> tuple:
    """cliente: lista de dicts {'img','ruta'}; internet: candidatas de ia.buscar_candidatas.
    Devuelve (elegidas_cliente, elegidas_internet, metodo) con metodo 'ia' o 'tamano'."""
    hay_clave = bool(config.get("openrouter_api_key") or config.get("gemini_api_key"))
    if usar_elegir and hay_clave and (cliente or internet) and len(cliente) + len(internet) > 1:
        items = cliente[:8] + internet[:max(0, 8 - len(cliente))]
        elegidas = ia.elegir_con_ia(items, nombre, maximo, config, avisar,
                                    n_cliente=min(len(cliente), 8), modo=modo)
        if elegidas:
            ids = {id(c) for c in cliente}
            return ([c for c in elegidas if id(c) in ids],
                    [c for c in elegidas if id(c) not in ids], "ia")
        avisar("La IA no eligió fotos; se usan las del cliente y las más grandes de internet.")
    if modo == "internet_primero" and internet:
        usadas_int = internet[:maximo]
        return cliente[:max(0, maximo - len(usadas_int))], usadas_int, "tamano"
    usadas_cliente = cliente[:maximo]
    cupo = max(0, min(2, maximo - len(usadas_cliente))) if cliente else maximo
    return usadas_cliente, internet[:cupo], "tamano"


CRLF = chr(13) + chr(10)
BOM = chr(0xFEFF).encode("utf-8")
COLS_PAQUETE = ["nombre", "fotos", "categoria", "descripcion", "precio", "clave"]


def clave_producto(nombre: str, carpeta) -> str:
    """Hash corto estable (nombre + carpeta) que el plugin usa para no duplicar productos."""
    return hashlib.md5(f"{nombre}|{carpeta}".encode("utf-8")).hexdigest()[:10]


def _csv_bytes(productos: list) -> bytes:
    """productos.csv en UTF-8 con BOM, con las columnas que lee el plugin."""
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator=CRLF)
    w.writerow(COLS_PAQUETE)
    for p in productos:
        w.writerow([p["nombre"], ";".join(p["fotos"]), p["categoria"], p["descripcion"],
                    p["precio"], p["clave"]])
    return BOM + out.getvalue().encode("utf-8")


def _partir_productos(productos: list, limite_bytes: int) -> list:
    """Reparte los productos en grupos que no pasen del límite (un producto nunca se parte)."""
    grupos, actual, peso = [], [], 0
    for p in productos:
        if actual and peso + p["peso"] > limite_bytes:
            grupos.append(actual)
            actual, peso = [], 0
        actual.append(p)
        peso += p["peso"]
    if actual:
        grupos.append(actual)
    return grupos


def crear_zips(productos: list, carpeta: Path, nombre_web: str, max_zip_mb: float,
               fotos_dir: Path) -> list:
    """Crea uno o varios ZIP (fotos/ + productos.csv) en la carpeta. Devuelve las rutas.
    Cada elemento de productos lleva 'peso' y 'fotos' (nombres de archivo en fotos_dir)."""
    try:
        limite = int(float(max_zip_mb) * 1024 * 1024)
    except (TypeError, ValueError):
        limite = 8 * 1024 * 1024
    grupos = _partir_productos(productos, max(limite, 1))
    sello = datetime.now().strftime("%Y%m%d-%H%M")
    base = f"productos-{imagenes.nombre_ascii(nombre_web)}-{sello}"
    rutas = []
    for n, grupo in enumerate(grupos, 1):
        nombre_zip = f"{base}.zip" if len(grupos) == 1 else f"{base}-parte{n}.zip"
        ruta = carpeta / nombre_zip
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("productos.csv", _csv_bytes(grupo))
            for p in grupo:
                for f in p["fotos"]:
                    z.write(fotos_dir / f, f"fotos/{f}")
        rutas.append(ruta)
    return rutas


def procesar(carpeta, sitio: dict, config: dict | None, usar_ia: bool = False,
             buscar_fotos: bool | None = None, log=print, detener=None, progreso=None) -> dict:
    # buscar_fotos queda por compatibilidad; ahora manda opciones.modo_fotos
    _preparar_log()
    carpeta = Path(carpeta)
    if config is None:
        config = cfg.cargar()

    def avisar(msg):
        logger.info(msg)
        log(msg)

    resumen = {"subidos": 0, "errores": 0, "pendientes": 0, "empaquetados": 0, "zips": []}
    paquete = sitio.get("entrega") == "paquete"
    ruta_xlsx = carpeta / "productos.xlsx"
    if not ruta_xlsx.exists():
        n_fotos = len(listar_fotos(carpeta))
        if not n_fotos:
            raise FileNotFoundError("La carpeta no tiene fotos ni productos.xlsx")
        crear_hoja_desde_fotos(carpeta)
        avisar(f"No había hoja: se creó productos.xlsx con {n_fotos} fotos (una fila por foto)")
    wb = openpyxl.load_workbook(ruta_xlsx)
    hoja = wb.worksheets[0]
    cols = mapear_columnas(hoja)

    tipo = sitio.get("tipo")
    wp = None if paquete else ClienteWP(sitio["url"], sitio.get("wp_usuario", ""),
                                        sitio.get("wp_app_password", ""))
    woo = None
    if paquete:
        if tipo not in ("woocommerce", "catalogo"):
            raise ValueError(f"Tipo de sitio desconocido: {tipo!r}")
    elif tipo == "woocommerce":
        woo = ClienteWoo(sitio["url"], sitio.get("wc_key", ""), sitio.get("wc_secret", ""))
        try:
            wp.probar()
            woo.modo_rest = wp.modo_rest
        except ErrorWeb:
            pass
    elif tipo == "catalogo":
        if not sitio.get("post_type"):
            raise ValueError("Falta el post_type del sitio. Usá 'Detectar tipo de contenido'.")
    else:
        raise ValueError(f"Tipo de sitio desconocido: {tipo!r}")

    conv_dir = carpeta / "convertidas"
    paq_dir = carpeta / "paquete"
    paq_fotos = paq_dir / "fotos"
    paq_productos = []   # productos ya listos para el ZIP (se marcan al crear el ZIP)
    if paquete:
        paq_fotos.mkdir(parents=True, exist_ok=True)
        for viejo in paq_fotos.glob("*.webp"):   # solo archivos que el programa generó antes
            try:
                viejo.unlink()
            except OSError:
                pass
    avisar(f"Sitio: {sitio.get('nombre')} ({tipo}"
           + (", paquete ZIP" if paquete else "") + f"). Hoja: {ruta_xlsx.name}")

    def celda(fila, col):
        return _texto(hoja.cell(row=fila, column=cols[col]).value) if col in cols else ""

    def poner(fila, col, valor):
        hoja.cell(row=fila, column=cols[col], value=valor)

    pendientes_filas = filas_a_procesar(hoja, cols)
    total = len(pendientes_filas)
    hechas = 0
    sin_nombre = 0

    def avanzar(nombre):
        if progreso:
            try:
                progreso(hechas, total, nombre)
            except Exception:
                pass

    opc = dict(cfg.OPCIONES_DEFECTO)
    opc.update(config.get("opciones") or {})
    elegir_mejores = bool(opc.get("elegir_mejores", True))
    modo = opc.get("modo_fotos") or "cliente_e_internet"
    try:
        maximo = max(1, int(opc.get("max_fotos") or 4))
    except (TypeError, ValueError):
        maximo = 4
    if opc.get("quitar_fondo") and not imagenes.quitador_disponible():
        opc["quitar_fondo"] = False
        avisar("AVISO: falta instalar el quitador de fondo (ejecute instalar.bat); "
               "se sigue sin quitar el fondo.")
    avanzar("")

    for fila in pendientes_filas:
        if detener is not None and detener.is_set():
            avisar("Proceso detenido por el usuario.")
            break

        notas = []
        nombre = ""
        try:
            nombre = celda(fila, "nombre")
            fotos = []
            for f in _separar_fotos(celda(fila, "fotos")):
                p = Path(f)
                p = p if p.is_absolute() else carpeta / p
                if p.exists():
                    fotos.append(p)
                else:
                    notas.append(f"falta la foto {f}")

            if not nombre and not fotos:
                poner(fila, "estado", "pendiente")
                poner(fila, "nota", "sin nombre ni fotos")
                resumen["pendientes"] += 1
                avisar(f"Fila {fila}: sin nombre ni fotos, queda pendiente.")
                _guardar(wb, ruta_xlsx, carpeta, avisar)
                hechas += 1
                avanzar(nombre)
                continue

            if not nombre:
                if not usar_ia:
                    poner(fila, "estado", "pendiente")
                    poner(fila, "nota", "sin nombre (IA desactivada)")
                    sin_nombre += 1
                    resumen["pendientes"] += 1
                    avisar(f"Fila {fila}: sin nombre y la IA está desactivada.")
                    _guardar(wb, ruta_xlsx, carpeta, avisar)
                    hechas += 1
                    avanzar(nombre)
                    continue
                try:
                    nombre, fuente = ia.sugerir_nombre(fotos[0], config)
                except ia.ErrorIA as e:
                    poner(fila, "estado", "pendiente")
                    poner(fila, "nota", f"no se pudo sugerir nombre: {e}")
                    resumen["pendientes"] += 1
                    avisar(f"Fila {fila}: {e}")
                    _guardar(wb, ruta_xlsx, carpeta, avisar)
                    hechas += 1
                    avanzar(nombre)
                    continue
                poner(fila, "nombre", nombre)
                notas.append(f"nombre sugerido por IA ({fuente})")

            # ----- decidir de dónde salen las fotos -----
            buscar = nombre and (modo in ("internet_primero", "cliente_e_internet")
                                 or (modo == "internet_si_faltan" and not fotos))
            candidatas, nota_lic = [], ""
            if buscar:
                avisar(f"Fila {fila}: buscando fotos de '{nombre}' en internet...")
                try:
                    candidatas, nota_lic = ia.buscar_candidatas(
                        nombre, config, opc.get("licencia") or "libre_primero", log=avisar)
                except Exception as e:
                    avisar(f"Fila {fila}: la búsqueda en internet falló ({e.__class__.__name__}).")
                    notas.append("búsqueda en internet falló")
                if nota_lic and not candidatas:
                    notas.append(nota_lic)

            if not fotos and not candidatas:
                poner(fila, "estado", "pendiente")
                poner(fila, "nota", "; ".join(notas + ["sin fotos"]))
                resumen["pendientes"] += 1
                avisar(f"Fila {fila}: '{nombre}' sin fotos, queda pendiente.")
                _guardar(wb, ruta_xlsx, carpeta, avisar)
                hechas += 1
                avanzar(nombre)
                continue

            avisar(f"Fila {fila}: {nombre} ({len(fotos)} foto/s del cliente"
                   + (f", {len(candidatas)} candidata/s de internet" if candidatas else "") + ")")
            cliente = []
            for foto in fotos:
                cliente.append({"img": _preparar_cliente(foto, opc, notas), "ruta": foto})

            el_cli, el_int, metodo = _elegir_fotos(
                nombre, cliente, candidatas, maximo, elegir_mejores, config, avisar, modo)

            finales = []  # imágenes PIL en orden, con su origen
            for c in el_cli:
                finales.append((c["img"], c["ruta"].stem))
            slug = imagenes.nombre_ascii(nombre)[:40] or "producto"
            for n, c in enumerate(el_int, 1):
                ruta = ia.guardar_foto(c, carpeta / "internet", slug, n)
                img = c["img"]
                if opc.get("arreglar_fotos"):
                    img = imagenes.arreglar(img)
                finales.append((img, ruta.stem))
            if not finales:
                raise ErrorWeb("ninguna foto quedó disponible para subir")

            partes = []
            if el_cli:
                partes.append(f"{len(el_cli)} del cliente")
            if el_int:
                partes.append(f"{len(el_int)} de internet")
            notas.append("fotos: " + " + ".join(partes)
                         + (" (elegidas por IA)" if metodo == "ia" and candidatas else ""))
            if el_int and nota_lic:
                notas.append(nota_lic)

            if paquete:
                nombres = []
                for n, (img, base) in enumerate(finales, 1):
                    webp = imagenes.guardar_webp(img, paq_fotos, f"{slug}-{n}")
                    nombres.append(webp.name)
                paq_productos.append({
                    "fila": fila, "nombre": nombre, "fotos": nombres,
                    "categoria": celda(fila, "categoria"),
                    "descripcion": celda(fila, "descripcion"),
                    "precio": celda(fila, "precio").replace("Q", "").replace(",", "").strip(),
                    "clave": clave_producto(nombre, carpeta),
                    "peso": sum((paq_fotos / f).stat().st_size for f in nombres),
                    "notas": notas})
                avisar(f"Fila {fila}: '{nombre}' listo para el paquete ({len(nombres)} foto/s).")
                _guardar(wb, ruta_xlsx, carpeta, avisar)
                hechas += 1
                avanzar(nombre)
                continue

            subidas = []
            for img, base in finales:
                webp = imagenes.guardar_webp(img, conv_dir, base)
                try:
                    subidas.append(wp.subir_medio(webp, nombre, nombre))
                except TipoNoPermitido:
                    jpg = conv_dir / (webp.stem + ".jpg")
                    img.convert("RGB").save(jpg, "JPEG", quality=85, optimize=True)
                    subidas.append(wp.subir_medio(jpg, nombre, nombre))
                    if "WebP rechazado, subido JPG" not in notas:
                        notas.append("WebP rechazado, subido JPG")

            if tipo == "woocommerce":
                cat_nombre = celda(fila, "categoria")
                cat_id = woo.categoria_id(cat_nombre) if cat_nombre else None
                precio = celda(fila, "precio").replace("Q", "").replace(",", "").strip() or None
                r = woo.crear_producto(nombre, [s["id"] for s in subidas],
                                       descripcion=celda(fila, "descripcion") or None,
                                       precio=precio, categoria_id=cat_id)
                nuevo_id = r["id"]
            else:
                contenido = _bloques_imagen(subidas[1:], nombre)
                desc = celda(fila, "descripcion")
                if desc:
                    contenido = f"<!-- wp:paragraph --><p>{desc}</p><!-- /wp:paragraph -->" + chr(10) + contenido
                r = wp.crear_entrada(sitio["post_type"], nombre, subidas[0]["id"], contenido)
                nuevo_id = r["id"]

            poner(fila, "estado", "subido")
            poner(fila, "id", nuevo_id)
            poner(fila, "enlace_edicion",
                  f"{sitio['url'].rstrip('/')}/wp-admin/post.php?post={nuevo_id}&action=edit")
            poner(fila, "nota", "; ".join(notas))
            resumen["subidos"] += 1
            avisar(f"Fila {fila}: subido como borrador (id {nuevo_id}).")
        except Exception as e:  # cualquier fallo de una fila no frena las demás
            if isinstance(e, (ErrorWeb, ia.ErrorIA)):
                msg = str(e)
            else:
                msg = f"{e.__class__.__name__}: {e}"
                logger.exception("Fila %s", fila)
            poner(fila, "estado", "error")
            poner(fila, "nota", "; ".join(notas + [msg]))
            resumen["errores"] += 1
            avisar(f"Fila {fila}: ERROR - {msg}")

        _guardar(wb, ruta_xlsx, carpeta, avisar)
        hechas += 1
        avanzar(nombre or celda(fila, "nombre"))
        time.sleep(0.5)

    if paquete and paq_productos:
        try:
            opc_mb = opc.get("max_zip_mb") or 8
            zips = crear_zips(paq_productos, carpeta, sitio.get("nombre", "web"), opc_mb, paq_fotos)
            (paq_dir / "productos.csv").write_bytes(_csv_bytes(paq_productos))
            # a qué ZIP quedó cada producto
            grupos = _partir_productos(paq_productos, max(int(float(opc_mb) * 1048576), 1))
            for ruta_zip, grupo in zip(zips, grupos):
                for p in grupo:
                    poner(p["fila"], "estado", "empaquetado")
                    poner(p["fila"], "id", None)
                    poner(p["fila"], "enlace_edicion", str(ruta_zip))
                    poner(p["fila"], "nota", "; ".join(p["notas"]))
                    resumen["empaquetados"] += 1
            resumen["zips"] = [str(z) for z in zips]
            _guardar(wb, ruta_xlsx, carpeta, avisar)
            for z in zips:
                avisar(f"ZIP creado: {z} ({z.stat().st_size / 1048576:.2f} MB)")
        except Exception as e:
            logger.exception("Crear ZIP")
            resumen["errores"] += len(paq_productos)
            for p in paq_productos:
                poner(p["fila"], "estado", "error")
                poner(p["fila"], "nota", f"no se pudo crear el ZIP: {e}")
            _guardar(wb, ruta_xlsx, carpeta, avisar)
            avisar(f"ERROR al crear el ZIP: {e}")

    if sin_nombre and not usar_ia:
        avisar(f"{sin_nombre} productos quedaron sin nombre: escribilos en productos.xlsx o "
               "activá 'Sugerir nombre con IA' y volvé a dar Subir")
    avisar(f"Listo. Subidos: {resumen['subidos']}, empaquetados: {resumen['empaquetados']}, "
           f"errores: {resumen['errores']}, pendientes: {resumen['pendientes']}.")
    return resumen
