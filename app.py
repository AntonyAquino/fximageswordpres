"""Subidor de productos: ventana principal (tkinter/ttk) con 4 pestañas."""
import os
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

import config
import ia
import imagenes
import subir
from wordpress import ClienteWP, ClienteWoo, ErrorWeb, MARCA_HOSTING, normalizar_url

CARPETA = Path(__file__).resolve().parent
PLANTILLA = CARPETA / "plantilla.xlsx"
EXT_FOTOS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}

VERDE, ROJO, GRIS = "#2e7d32", "#c62828", "#9e9e9e"
COLORES = {"ok": VERDE, "error": ROJO, "gris": GRIS}

MODOS_FOTOS = [
    ("internet_primero", "Internet primero: fotos de catálogo del producto; las del cliente solo si no hay buenas (recomendado para productos de marca)"),
    ("cliente_e_internet", "Fotos del cliente primero; internet solo para completar"),
    ("cliente", "Solo fotos del cliente"),
    ("internet_si_faltan", "Internet solo cuando la fila no tiene fotos"),
]
GUIA_CLIENTE = CARPETA / "guia-fotos-para-clientes.txt"
CONSEJOS_FOTOS = (
    "• Luz natural de día, sin flash.\n"
    "• Fondo liso y claro (pared blanca, hoja o tela lisa).\n"
    "• Sacar el producto de la vitrina.\n"
    "• Limpiar el envase antes de la foto.\n"
    "• Celular a la altura del producto, con la mano firme.\n"
    "• Una foto de frente por producto.")
LICENCIAS = [
    ("libre", "Solo fotos de libre uso (puede no encontrar nada)"),
    ("libre_primero", "Libre uso primero; si no hay, cualquiera y lo anota en la hoja (recomendado)"),
    ("cualquiera", "Cualquier foto (revisar derechos antes de publicar)"),
]

MODELOS_OPENROUTER = ["openrouter/free", "nvidia/nemotron-3.5-super-vl:free",
                      "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free"]
MODELOS_GEMINI = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

AYUDA_WEB = ("Si la web está en InfinityFree (o un hosting que bloquea la API), elegí Entrega → "
             "Paquete ZIP: no hace falta ninguna clave.\n"
             "Dónde se crea cada dato (solo para entrega por API):\n"
             "• Contraseña de aplicación: en el panel de la web, Usuarios → Perfil → "
             "Contraseñas de aplicación → escribí un nombre y presioná Añadir.\n"
             "• Clave y Secreto de WooCommerce: WooCommerce → Ajustes → Avanzado → REST API → "
             "Añadir clave, con permiso Lectura/Escritura.\n"
             "• El usuario de una tienda debe tener el rol Gerente de tienda (o Administrador). "
             "En un catálogo basta con Editor.")

TEXTO_AYUDA = [
    ("Cómo funciona", "1. El cliente te manda las fotos de sus productos.\n"
     "2. Las ponés en una carpeta. Camino corto: solo las fotos, sin hoja.\n"
     "3. En la pestaña Subir productos elegís la web y la carpeta, y presionás Subir productos. "
     "Si no hay productos.xlsx, la app lo arma sola con una fila por foto y, con la IA activa, "
     "les pone nombre.\n"
     "4. La hoja es opcional: sirve para poner nombres, precios y categorías, o para juntar varias "
     "fotos de un mismo producto (columna 'fotos' separada por ;). El botón 'Crear hoja en esta "
     "carpeta' la arma con tus fotos.\n"
     "5. El programa crea cada producto como borrador (o ZIP); el cliente lo revisa y publica."),
    ("Paquete ZIP con el plugin (InfinityFree)", "Para webs que bloquean la API, en la pestaña Webs elegí "
     "Entrega → Paquete ZIP. La app hace todo igual (nombres, fotos, arreglo, WebP) pero en vez de subir "
     "crea uno o varios ZIP en la carpeta (paquete-nombre-fecha.zip). Si pesan más del máximo (8 MB) se parten "
     "en -parte1, -parte2…\n"
     "Instalar el plugin, una sola vez por web: en el panel de WordPress, Plugins → Añadir nuevo → Subir "
     "plugin, y elegí plugin\\subidor-productos.zip (está en la carpeta del programa).\n"
     "Cada vez: Herramientas → Subidor de productos, subí el ZIP y revisá la tabla de resultados. "
     "Los productos quedan en borrador. Si se corta, volvé a subir el mismo ZIP: omite los que ya existen."),
    ("Estados de la hoja", "• empaquetado: el producto ya está en un ZIP (la columna enlace_edicion dice cuál). "
     "No se vuelve a empaquetar.\n"
     "• subido: el producto ya se creó como borrador. No se vuelve a subir.\n"
     "• pendiente: faltó el nombre o las fotos. Completá la fila y volvé a subir.\n"
     "• error: algo falló; leé la columna nota. Corregí y borrá el estado para reintentar."),
    ("Si falta el nombre o las fotos", "• Sin nombre y con fotos: si la casilla de IA está marcada, "
     "la IA sugiere un nombre viendo la primera foto. Si no, queda pendiente.\n"
     "• Sin fotos y sin nada en internet: queda pendiente.\n"
     "• De dónde salen las fotos lo decidís en el paso 3: solo las del cliente, las del cliente más "
     "internet (recomendado, la IA elige las mejores), o internet solo si la fila no tiene fotos."),
    ("Fotos de internet y licencias", "En la pestaña Inteligencia artificial elegís cómo buscar:\n"
     "• Solo fotos de libre uso: usa el filtro de uso comercial del buscador; si no hay, no usa "
     "internet y lo anota.\n"
     "• Libre uso primero (recomendado): igual, pero si no hay ninguna busca sin filtro y la nota "
     "dice 'fotos sin licencia confirmada, reemplazar por fotos del cliente'.\n"
     "• Cualquier foto: sin filtro; la nota pide revisar derechos de autor.\n"
     "El filtro depende de lo que cada sitio declare; no es una garantía legal. Cada foto bajada "
     "queda registrada en internet\\fuentes.txt con su dirección y si pasó el filtro."),
    ("Arreglo automático de fotos", "Las fotos del cliente se arreglan solas: luz, contraste, color "
     "y nitidez, y el fondo se cambia por blanco tipo catálogo. Las de internet solo se arreglan. "
     "Con 'Vista previa de una foto…' ves el antes y el después. Si una foto queda mal, reemplazala "
     "en el panel de la web (Medios) o desmarcá las casillas y volvé a subir ese producto. "
     "La primera vez que se quita un fondo, el programa descarga un modelo de unos 170 MB "
     "(solo una vez, hace falta internet)."),
    ("Derechos de autor", "Las fotos que salen de internet pueden tener derechos de autor. "
     "Revisalas antes de publicar, o pedile al cliente sus propias fotos. "
     "La columna nota de la hoja lo recuerda en cada producto."),
    ("Registro", "Todo lo que hace el programa queda anotado en el archivo registro.log, "
     "dentro de la carpeta del programa."),
]


def resumir_carpeta(carpeta) -> tuple:
    """Devuelve (texto de resumen, existe_xlsx) para el paso 2."""
    carpeta = Path(carpeta)
    fotos = len(subir.listar_fotos(carpeta))
    ruta = carpeta / "productos.xlsx"
    if not ruta.exists():
        if fotos:
            return (f"{fotos} fotos · no hay hoja: se creará sola al dar Subir "
                    "(una fila por foto)"), False
        return "La carpeta no tiene fotos", False
    try:
        import openpyxl
        wb = openpyxl.load_workbook(ruta, data_only=True)
        hoja = wb.worksheets[0]
        total = sum(1 for f in range(2, hoja.max_row + 1)
                    if any(subir._texto(hoja.cell(row=f, column=c).value)
                           for c in range(1, hoja.max_column + 1)))
        cols = subir.mapear_columnas(hoja)
        pend = len(subir.filas_a_procesar(hoja, cols))
        return f"{fotos} fotos · productos.xlsx con {total} productos ({pend} pendientes de subir)", True
    except ValueError as e:
        return f"{fotos} fotos · productos.xlsx: {e}", True
    except Exception:
        return f"{fotos} fotos · productos.xlsx existe pero no se pudo leer (¿está abierto?)", True


def _msg_error(e) -> str:
    if isinstance(e, (ErrorWeb, ia.ErrorIA)):
        return str(e)
    return f"Ocurrió un error inesperado ({e.__class__.__name__})."


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Subidor de productos")
        # Ajustar la altura a la pantalla (laptops de 768 px de alto)
        alto = min(820, self.winfo_screenheight() - 90)
        self.geometry(f"900x{alto}")
        self.minsize(820, min(700, alto))
        self.cola = queue.Queue()
        self.hilo = None
        self.detener_ev = threading.Event()
        try:
            self.datos = config.cargar()
        except (OSError, ValueError) as e:
            messagebox.showerror("Error", f"No se pudo leer sitios.json: {e}\n"
                                          "Se empieza con una configuración vacía.")
            self.datos = config.vacio()
        self._estilos()
        self._armar()
        self.refrescar_sitios()
        self.refrescar_ia_disponible()
        self.after(200, self._vaciar_cola)

    # ---------- estilo y utilidades ----------
    def _estilos(self):
        st = ttk.Style(self)
        st.theme_use("vista" if "vista" in st.theme_names() else "clam")
        for nombre in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(nombre).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass
        st.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"))
        st.configure("Gris.TLabel", foreground="#757575", font=("Segoe UI", 9))
        st.configure("Grande.TButton", padding=10, font=("Segoe UI", 11, "bold"))
        st.configure("TNotebook.Tab", padding=(14, 6))

    @staticmethod
    def poner_estado(lbl, nivel, texto):
        lbl.configure(text=f"● {texto}", foreground=COLORES[nivel])

    def _indicador(self, padre, texto="Sin probar"):
        lbl = ttk.Label(padre)
        self.poner_estado(lbl, "gris", texto)
        return lbl

    def _hilo(self, trabajo, listo):
        """Corre trabajo() en un hilo y llama listo(resultado, error) en la ventana."""
        def run():
            try:
                res = trabajo()
                self.cola.put(("llamar", lambda: listo(res, None)))
            except Exception as e:
                self.cola.put(("llamar", lambda e=e: listo(None, e)))
        threading.Thread(target=run, daemon=True).start()

    def _vaciar_cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "log":
                    self.escribir(dato)
                elif tipo == "prog":
                    self._progreso(*dato)
                elif tipo == "llamar":
                    dato()
                elif tipo == "fin":
                    self._terminar(dato)
        except queue.Empty:
            pass
        self.after(200, self._vaciar_cola)

    def escribir(self, msg):
        self.texto.configure(state="normal")
        self.texto.insert("end", msg + "\n")
        self.texto.see("end")
        self.texto.configure(state="disabled")

    def guardar_datos(self) -> bool:
        try:
            config.guardar(self.datos)
            return True
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo guardar sitios.json: {e}")
            return False

    # ---------- armado general ----------
    def _armar(self):
        self.estado = tk.StringVar(value="Listo.")
        ttk.Label(self, textvariable=self.estado, relief="sunken", anchor="w",
                  padding=(8, 3)).pack(fill="x", side="bottom")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.t_subir = ttk.Frame(self.notebook, padding=10)
        self.t_webs = ttk.Frame(self.notebook, padding=10)
        self.t_ia = ttk.Frame(self.notebook, padding=10)
        self.t_ayuda = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.t_subir, text="Subir productos")
        self.notebook.add(self.t_webs, text="Webs")
        self.notebook.add(self.t_ia, text="Inteligencia artificial")
        self.notebook.add(self.t_ayuda, text="Ayuda")
        self._armar_subir()
        self._armar_webs()
        self._armar_ia()
        self._armar_ayuda()

    # =====================================================================
    # Pestaña 1: Subir productos
    # =====================================================================
    def _armar_subir(self):
        p = self.t_subir
        self.carpeta = tk.StringVar()
        opc = self.datos["opciones"]
        self.v_usar_ia = tk.BooleanVar(value=bool(opc.get("usar_ia")))
        self.v_modo = tk.StringVar(value=opc.get("modo_fotos") or "internet_primero")
        self.v_licencia = tk.StringVar(value=opc.get("licencia") or "libre_primero")
        self.v_maxfotos = tk.StringVar(value=str(opc.get("max_fotos") or 4))
        self.v_arreglar = tk.BooleanVar(value=bool(opc.get("arreglar_fotos", True)))
        self.v_quitar = tk.BooleanVar(value=bool(opc.get("quitar_fondo", True)))
        self.v_mejores = tk.BooleanVar(value=bool(opc.get("elegir_mejores", True)))

        # Paso 1
        f1 = ttk.LabelFrame(p, text="Paso 1 · Elegí la web", padding=8)
        f1.pack(fill="x")
        self.f1_con = ttk.Frame(f1)
        self.combo = ttk.Combobox(self.f1_con, state="readonly", width=32)
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._sitio_cambio())
        self.ind_conexion = self._indicador(self.f1_con)
        self.ind_conexion.pack(side="left", padx=10)
        self.b_probar = ttk.Button(self.f1_con, text="Probar", command=self.probar_sitio)
        self.b_probar.pack(side="left")
        self.lbl_tipo = ttk.Label(f1, style="Gris.TLabel")
        self.f1_vacio = ttk.Frame(f1)
        ttk.Label(self.f1_vacio, text="Todavía no hay webs. Agregá una en la pestaña Webs."
                  ).pack(side="left")
        ttk.Button(self.f1_vacio, text="Ir a Webs",
                   command=lambda: self.notebook.select(self.t_webs)).pack(side="left", padx=10)

        # Paso 2
        f2 = ttk.LabelFrame(p, text="Paso 2 · Elegí la carpeta con las fotos y la hoja", padding=8)
        f2.pack(fill="x", pady=(8, 0))
        fila = ttk.Frame(f2)
        fila.pack(fill="x")
        ttk.Button(fila, text="Elegir carpeta…", command=self.elegir_carpeta).pack(side="left")
        ttk.Entry(fila, textvariable=self.carpeta, state="readonly").pack(
            side="left", fill="x", expand=True, padx=8)
        fila2 = ttk.Frame(f2)
        fila2.pack(fill="x", pady=(6, 0))
        self.lbl_resumen = ttk.Label(fila2, text="Todavía no elegiste ninguna carpeta.",
                                     style="Gris.TLabel")
        self.lbl_resumen.pack(side="left")
        self.b_crear_hoja = ttk.Button(fila2, text="Crear hoja en esta carpeta",
                                       command=self.crear_hoja)
        self.b_abrir_hoja = ttk.Button(fila2, text="Abrir hoja", command=self.abrir_hoja)
        ttk.Label(f2, text="Podés dar Subir con solo las fotos en la carpeta: la app arma la hoja "
                  "y, con la IA activa, les pone nombre.", style="Gris.TLabel").pack(
            anchor="w", pady=(4, 0))

        # Paso 3
        f3 = ttk.LabelFrame(p, text="Paso 3 · Opciones", padding=8)
        f3.pack(fill="x", pady=(8, 0))
        self.c_usar_ia = ttk.Checkbutton(
            f3, text="Sugerir nombre con IA cuando la fila no tiene nombre",
            variable=self.v_usar_ia, command=self.guardar_opciones)
        self.c_usar_ia.pack(anchor="w")
        self.c_mejores = ttk.Checkbutton(
            f3, text="Elegir las mejores fotos con IA (recomendado)",
            variable=self.v_mejores, command=self.guardar_opciones)
        self.c_mejores.pack(anchor="w")
        self.lbl_sin_ia = ttk.Label(f3, text="Agregá una clave en la pestaña Inteligencia artificial",
                                    style="Gris.TLabel")

        ttk.Label(f3, text="¿De dónde salen las fotos de cada producto?",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 0))
        for valor, texto in MODOS_FOTOS:
            ttk.Radiobutton(f3, text=texto, value=valor, variable=self.v_modo,
                            command=self.guardar_opciones).pack(anchor="w", padx=(14, 0))
        fmax = ttk.Frame(f3)
        fmax.pack(anchor="w", pady=(4, 0))
        ttk.Label(fmax, text="Máximo de fotos por producto:").pack(side="left")
        self.sp_max = ttk.Spinbox(fmax, from_=1, to=10, width=4, textvariable=self.v_maxfotos,
                                  command=self.guardar_opciones)
        self.sp_max.pack(side="left", padx=6)
        self.sp_max.bind("<FocusOut>", lambda e: self.guardar_opciones())
        self.sp_max.bind("<Return>", lambda e: self.guardar_opciones())

        ttk.Checkbutton(f3, text="Arreglar fotos del cliente (luz, contraste, nitidez)",
                        variable=self.v_arreglar, command=self.guardar_opciones
                        ).pack(anchor="w", pady=(8, 0))
        self.c_quitar = ttk.Checkbutton(
            f3, text="Quitar el fondo y ponerlo blanco, tipo catálogo (recomendado)",
            variable=self.v_quitar, command=self.guardar_opciones)
        self.c_quitar.pack(anchor="w")
        self.hay_quitador = imagenes.quitador_disponible()
        if not self.hay_quitador:
            self.c_quitar.configure(state="disabled")
            ttk.Label(f3, text="Falta instalar el quitador de fondo: ejecutá instalar.bat",
                      style="Gris.TLabel").pack(anchor="w", padx=(22, 0))
        self.b_vista = ttk.Button(f3, text="Vista previa de una foto…", command=self.vista_previa)
        self.b_vista.pack(anchor="w", pady=(6, 0))

        # Paso 4
        f4 = ttk.LabelFrame(p, text="Paso 4 · Subir", padding=8)
        f4.pack(fill="x", pady=(8, 0))
        fb = ttk.Frame(f4)
        fb.pack(fill="x")
        self.b_subir = ttk.Button(fb, text="Subir productos", style="Grande.TButton",
                                  command=self.iniciar)
        self.b_subir.pack(side="left")
        self.b_detener = ttk.Button(fb, text="Detener", command=self.detener, state="disabled")
        self.b_detener.pack(side="left", padx=10)
        self.barra = ttk.Progressbar(f4, mode="determinate", maximum=1, value=0)
        self.barra.pack(fill="x", pady=(8, 2))
        self.lbl_prog = ttk.Label(f4, text="", style="Gris.TLabel")
        self.lbl_prog.pack(anchor="w")

        self.texto = ScrolledText(p, height=6, state="disabled", wrap="word")
        self.texto.pack(fill="both", expand=True, pady=(8, 0))

    def refrescar_sitios(self):
        sitios = self.datos.get("sitios", [])
        nombres = [s.get("nombre", "(sin nombre)") for s in sitios]
        self.combo["values"] = nombres
        if nombres:
            actual = self.combo.get()
            self.combo.set(actual if actual in nombres else nombres[0])
            self.f1_vacio.pack_forget()
            self.f1_con.pack(anchor="w")
            self.lbl_tipo.pack(anchor="w", pady=(4, 0))
        else:
            self.combo.set("")
            self.f1_con.pack_forget()
            self.lbl_tipo.pack_forget()
            self.f1_vacio.pack(anchor="w")
        self._sitio_cambio(reiniciar=False)

    def _sitio_cambio(self, reiniciar=True):
        s = self.sitio_actual()
        if reiniciar:
            self.poner_estado(self.ind_conexion, "gris", "Sin probar")
        if not s:
            self.lbl_tipo.configure(text="")
        else:
            if s.get("tipo") == "woocommerce":
                txt = "Tipo: tienda WooCommerce"
            else:
                txt = f"Tipo: catálogo (post type: {s.get('post_type') or 'sin definir'})"
            if s.get("entrega") == "paquete":
                txt = ("Tipo: " + ("tienda" if s.get("tipo") == "woocommerce" else "catálogo")
                       + " · entrega: paquete ZIP para el plugin")
            self.lbl_tipo.configure(text=txt)

    def sitio_actual(self):
        nombre = self.combo.get()
        for s in self.datos.get("sitios", []):
            if s.get("nombre") == nombre:
                return s
        return None

    def hay_clave_ia(self) -> bool:
        return bool(self.datos.get("openrouter_api_key") or self.datos.get("gemini_api_key"))

    def refrescar_ia_disponible(self):
        hay = self.hay_clave_ia()
        estado = "normal" if hay else "disabled"
        self.c_usar_ia.configure(state=estado)
        self.c_mejores.configure(state=estado)
        if hay:
            self.lbl_sin_ia.pack_forget()
        else:
            self.lbl_sin_ia.pack(anchor="w", after=self.c_mejores)

    def guardar_opciones(self):
        try:
            maximo = max(1, min(10, int(self.v_maxfotos.get())))
        except (TypeError, ValueError):
            maximo = 4
        self.datos["opciones"].update({
            "usar_ia": self.v_usar_ia.get(),
            "elegir_mejores": self.v_mejores.get(),
            "modo_fotos": self.v_modo.get(),
            "licencia": self.v_licencia.get(),
            "max_fotos": maximo,
            "arreglar_fotos": self.v_arreglar.get(),
            "quitar_fondo": self.v_quitar.get() and self.hay_quitador,
        })
        try:
            config.guardar(self.datos)
        except OSError:
            pass

    # ---------- vista previa de una foto ----------
    def vista_previa(self):
        ruta = filedialog.askopenfilename(
            title="Elegí una foto para probar",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.bmp *.tif *.tiff"),
                       ("Todos", "*.*")])
        if not ruta:
            return
        arreglar = self.v_arreglar.get()
        quitar = self.v_quitar.get() and self.hay_quitador
        self.b_vista.configure(state="disabled")
        self.estado.set("Preparando la vista previa (el quitador de fondo puede tardar)…")

        def trabajo():
            antes = imagenes.abrir_rgb(Path(ruta))
            despues = antes.copy()
            aviso = ""
            if arreglar:
                despues = imagenes.arreglar(despues)
            if quitar:
                try:
                    despues = imagenes.quitar_fondo(despues)
                except Exception as e:
                    aviso = f"No se pudo quitar el fondo ({e.__class__.__name__})."
            return antes, despues, aviso

        def listo(res, err):
            self.b_vista.configure(state="normal")
            if err:
                self.estado.set("Listo.")
                messagebox.showerror("Error", f"No se pudo abrir la foto: {err}")
                return
            self.estado.set("Listo.")
            self._ventana_vista(Path(ruta).stem, *res)

        self._hilo(trabajo, listo)

    def _ventana_vista(self, nombre, antes, despues, aviso=""):
        win = tk.Toplevel(self)
        win.title("Vista previa")
        win.transient(self)
        marco = ttk.Frame(win, padding=10)
        marco.pack(fill="both", expand=True)
        win._fotos = []   # evita que Python borre las imágenes
        for col, (titulo, img) in enumerate((("Antes", antes), ("Después", despues))):
            mini = img.copy()
            mini.thumbnail((380, 380))
            tkimg = ImageTk.PhotoImage(mini)
            win._fotos.append(tkimg)
            ttk.Label(marco, text=titulo, font=("Segoe UI", 10, "bold")).grid(row=0, column=col)
            ttk.Label(marco, image=tkimg).grid(row=1, column=col, padx=6, pady=4)
        if aviso:
            ttk.Label(marco, text=aviso, foreground=ROJO).grid(row=2, column=0, columnspan=2)

        def guardar():
            destino = filedialog.asksaveasfilename(
                parent=win, defaultextension=".webp", initialfile=f"{nombre}-arreglada.webp",
                filetypes=[("WebP", "*.webp"), ("JPG", "*.jpg"), ("PNG", "*.png")])
            if not destino:
                return
            try:
                despues.convert("RGB").save(destino, quality=90)
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar: {e}", parent=win)

        fb = ttk.Frame(marco)
        fb.grid(row=3, column=0, columnspan=2, pady=(6, 0))
        ttk.Button(fb, text="Guardar como…", command=guardar).pack(side="left", padx=4)
        ttk.Button(fb, text="Cerrar", command=win.destroy).pack(side="left", padx=4)
        return win

    def probar_sitio(self):
        s = self.sitio_actual()
        if not s:
            messagebox.showwarning("Falta elegir", "Elegí una web primero.")
            return
        if s.get("entrega") == "paquete":
            messagebox.showinfo("Modo paquete", "Esta web usa paquete ZIP: no hace falta probar la conexión.")
            return
        self.poner_estado(self.ind_conexion, "gris", "Probando…")
        self._hilo(lambda: self._probar_credenciales(s), self._fin_probar_sitio)

    def _fin_probar_sitio(self, res, err):
        if err:
            self.poner_estado(self.ind_conexion, "error", "Falló")
            self.escribir(f"Conexión: {_msg_error(err)}")
            s = self.sitio_actual()
            if not self._aviso_hosting(err, s.get("nombre") if s else None):
                messagebox.showerror("Conexión", _msg_error(err))
        else:
            self.poner_estado(self.ind_conexion, "ok", "Conectado")
            self.escribir(res.replace("\n", " "))

    def elegir_carpeta(self):
        c = filedialog.askdirectory(title="Carpeta con las fotos y productos.xlsx")
        if c:
            self.carpeta.set(str(Path(c)))
            self.actualizar_resumen()

    def actualizar_resumen(self):
        c = self.carpeta.get()
        for b in (self.b_crear_hoja, self.b_abrir_hoja):
            b.pack_forget()
        if not c or not Path(c).is_dir():
            self.lbl_resumen.configure(text="Todavía no elegiste ninguna carpeta.")
            return
        texto, existe = resumir_carpeta(c)
        self.lbl_resumen.configure(text=texto)
        if existe:
            self.b_abrir_hoja.pack(side="left", padx=10)
        else:
            self.b_crear_hoja.pack(side="left", padx=10)

    def crear_hoja(self):
        c = Path(self.carpeta.get())
        destino = c / "productos.xlsx"
        if destino.exists():
            self.actualizar_resumen()
            if messagebox.askyesno("La hoja ya existe", "Ya hay un productos.xlsx en esa carpeta. "
                                   "¿Querés abrirlo?"):
                self.abrir_hoja()
            return
        try:
            if subir.listar_fotos(c):
                _, n = subir.crear_hoja_desde_fotos(c)
                self.escribir(f"Se creó {destino} con {n} fotos")
                messagebox.showinfo(
                    "Hoja creada", f"Hoja creada con {n} fotos, una fila por foto. "
                    "Si varias fotos son del mismo producto, poné sus nombres juntos en la "
                    "columna 'fotos' separados por ; . Dejá 'nombre' vacío para que la IA lo sugiera.")
            else:
                shutil.copyfile(PLANTILLA, destino)
                self.escribir(f"Se creó {destino}")
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo crear la hoja: {e}")
            return
        self.actualizar_resumen()
        self.abrir_hoja()

    def abrir_hoja(self):
        try:
            os.startfile(Path(self.carpeta.get()) / "productos.xlsx")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la hoja: {e}")

    # ---------- subida ----------
    def iniciar(self):
        s = self.sitio_actual()
        if not s:
            messagebox.showwarning("Falta elegir", "Elegí una web en el paso 1.")
            return
        if not self.carpeta.get() or not Path(self.carpeta.get()).is_dir():
            messagebox.showwarning("Falta la carpeta", "Elegí la carpeta con las fotos (paso 2).")
            return
        if (not (Path(self.carpeta.get()) / "productos.xlsx").exists()
                and not subir.listar_fotos(self.carpeta.get())):
            messagebox.showwarning("Carpeta vacía", "La carpeta no tiene fotos ni productos.xlsx.")
            return
        if self.hilo and self.hilo.is_alive():
            return
        self.detener_ev.clear()
        self.b_subir.configure(state="disabled")
        self.b_detener.configure(state="normal")
        self.estado.set("Subiendo…")
        self.barra.configure(value=0, maximum=1)
        self.lbl_prog.configure(text="Preparando…")
        carpeta = Path(self.carpeta.get())
        hay = self.hay_clave_ia()
        usar_ia = self.v_usar_ia.get() and hay
        self.guardar_opciones()
        cfg = dict(self.datos)
        cfg["opciones"] = dict(self.datos["opciones"])
        cfg["opciones"]["elegir_mejores"] = self.v_mejores.get() and hay

        def trabajo():
            try:
                res = subir.procesar(
                    carpeta, s, cfg, usar_ia,
                    log=lambda m: self.cola.put(("log", str(m))),
                    detener=self.detener_ev,
                    progreso=lambda h, t, n: self.cola.put(("prog", (h, t, n))))
                self.cola.put(("fin", res))
            except Exception as e:
                self.cola.put(("log", f"ERROR: {e}"))
                self.cola.put(("fin", {"fallo": str(e)}))

        self.hilo = threading.Thread(target=trabajo, daemon=True)
        self.hilo.start()

    def _progreso(self, hechas, total, nombre):
        self.barra.configure(maximum=max(total, 1), value=hechas)
        if total == 0:
            self.lbl_prog.configure(text="No hay filas para procesar.")
        elif hechas == 0:
            self.lbl_prog.configure(text=f"Producto 1 de {total}…")
        else:
            self.lbl_prog.configure(text=f"Producto {hechas} de {total}: {nombre}")

    def detener(self):
        self.detener_ev.set()
        self.estado.set("Deteniendo después del producto actual…")

    def _terminar(self, res):
        self.b_subir.configure(state="normal")
        self.b_detener.configure(state="disabled")
        if "fallo" in res:
            self.estado.set("Terminó con un error.")
            messagebox.showerror("Error", res["fallo"])
            return
        if res.get("zips") or res.get("empaquetados"):
            txt = (f"Empaquetados: {res['empaquetados']}   Errores: {res['errores']}   "
                   f"Pendientes: {res['pendientes']}   ZIP creados: {len(res['zips'])}")
            varios = len(res["zips"]) > 1
            rutas = "\n".join(res["zips"])
            extra = (f"\n\nArchivo{'s' if varios else ''} creado{'s' if varios else ''}:\n{rutas}"
                     "\n\nEste ZIP es el paquete de productos. Se sube en la web en Herramientas → "
                     "Subidor de productos" + (" (uno por uno, en orden)" if varios else "") +
                     ". (El plugin es otro archivo: plugin\\subidor-productos.zip, se instala una "
                     "sola vez desde Plugins → Añadir nuevo)")
        else:
            txt = (f"Subidos: {res['subidos']}   Errores: {res['errores']}   "
                   f"Pendientes: {res['pendientes']}")
            extra = ""
        self.estado.set(txt)
        self.actualizar_resumen()
        if messagebox.askyesno("Proceso terminado", f"{txt}{extra}\n\n¿Querés abrir la carpeta?"):
            try:
                os.startfile(self.carpeta.get())
            except Exception:
                pass

    # =====================================================================
    # Pestaña 2: Webs
    # =====================================================================
    def _armar_webs(self):
        p = self.t_webs
        izq = ttk.Frame(p)
        izq.pack(side="left", fill="y")
        ttk.Label(izq, text="Tus webs", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.lista = tk.Listbox(izq, width=24, exportselection=False, activestyle="none")
        self.lista.pack(fill="y", expand=True, pady=4)
        self.lista.bind("<<ListboxSelect>>", lambda e: self._elegir_en_lista())
        ttk.Button(izq, text="Nueva web", command=self.nueva_web).pack(fill="x", pady=2)
        ttk.Button(izq, text="Eliminar", command=self.eliminar_web).pack(fill="x", pady=2)

        der = ttk.Frame(p)
        der.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.web_idx = None
        self.w_nombre = tk.StringVar()
        self.w_url = tk.StringVar()
        self.w_tipo = tk.StringVar(value="woocommerce")
        self.w_entrega = tk.StringVar(value="api")
        self.w_usuario = tk.StringVar()
        self.w_pass = tk.StringVar()
        self.w_ck = tk.StringVar()
        self.w_cs = tk.StringVar()
        self.w_post = tk.StringVar()
        self.w_ver = tk.BooleanVar(value=False)

        form = ttk.Frame(der)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(form, text="Nombre").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.w_nombre).grid(row=r, column=1, sticky="ew", pady=3)
        r += 1
        ttk.Label(form, text="URL").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.w_url).grid(row=r, column=1, sticky="ew", pady=3)
        r += 1
        ttk.Label(form, text="Solo la dirección principal, por ejemplo https://mitienda.com (sin /wp-admin)", style="Gris.TLabel"
                  ).grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(form, text="Tipo").grid(row=r, column=0, sticky="w", pady=3)
        ft = ttk.Frame(form)
        ft.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Radiobutton(ft, text="Tienda WooCommerce", value="woocommerce",
                        variable=self.w_tipo, command=self._tipo_web).pack(side="left")
        ttk.Radiobutton(ft, text="Catálogo", value="catalogo",
                        variable=self.w_tipo, command=self._tipo_web).pack(side="left", padx=14)
        r += 1
        ttk.Label(form, text="Entrega").grid(row=r, column=0, sticky="nw", pady=3)
        fe = ttk.Frame(form)
        fe.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Radiobutton(fe, text="Subir por API (hosting normal)", value="api",
                        variable=self.w_entrega, command=self._tipo_web).pack(anchor="w")
        ttk.Radiobutton(fe, text="Paquete ZIP para el plugin (InfinityFree u hosting que bloquea la API)",
                        value="paquete", variable=self.w_entrega,
                        command=self._tipo_web).pack(anchor="w")
        r += 1
        # Credenciales: solo se piden en modo API
        self.f_cred = ttk.Frame(form)
        self.f_cred.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.f_cred.columnconfigure(1, weight=1)
        self.f_cred.grid_columnconfigure(0, minsize=150)
        ttk.Label(self.f_cred, text="Usuario de WordPress").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(self.f_cred, textvariable=self.w_usuario).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(self.f_cred, text="Contraseña de aplicación").grid(row=1, column=0, sticky="w", pady=3)
        fp = ttk.Frame(self.f_cred)
        fp.grid(row=1, column=1, sticky="ew", pady=3)
        self.e_pass = ttk.Entry(fp, textvariable=self.w_pass, show="•")
        self.e_pass.pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(fp, text="Mostrar", variable=self.w_ver,
                        command=self._mostrar_claves).pack(side="left", padx=8)
        self.lbl_paquete = ttk.Label(form, style="Gris.TLabel", wraplength=560, justify="left",
                                     text="Modo paquete: no se piden contraseñas ni claves. La app arma un ZIP "
                                          "y lo subís desde Herramientas → Subidor de productos de esa web.")
        self.lbl_paquete.grid(row=r, column=0, columnspan=2, sticky="w", pady=3)
        r += 1
        # Campos de tienda
        self.f_woo = ttk.Frame(form)
        self.f_woo.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.f_woo.columnconfigure(1, weight=1)
        ttk.Label(self.f_woo, text="Clave (ck_)").grid(row=0, column=0, sticky="w", pady=3)
        self.e_ck = ttk.Entry(self.f_woo, textvariable=self.w_ck, show="•")
        self.e_ck.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(self.f_woo, text="Secreto (cs_)").grid(row=1, column=0, sticky="w", pady=3)
        self.e_cs = ttk.Entry(self.f_woo, textvariable=self.w_cs, show="•")
        self.e_cs.grid(row=1, column=1, sticky="ew", pady=3)
        self.f_woo.grid_columnconfigure(0, minsize=150)
        # Campos de catálogo
        self.f_cat = ttk.Frame(form)
        self.f_cat.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.f_cat.columnconfigure(1, weight=1)
        ttk.Label(self.f_cat, text="Post type").grid(row=0, column=0, sticky="w", pady=3)
        self.c_post = ttk.Combobox(self.f_cat, textvariable=self.w_post)
        self.c_post.grid(row=0, column=1, sticky="ew", pady=3)
        self.c_post.bind("<<ComboboxSelected>>", self._elegir_post)
        self.b_detectar = ttk.Button(self.f_cat, text="Detectar…", command=self.detectar_tipos)
        self.b_detectar.grid(row=0, column=2, padx=(8, 0))
        self.f_cat.grid_columnconfigure(0, minsize=150)
        form.grid_columnconfigure(0, minsize=150)

        botones = ttk.Frame(der)
        botones.pack(fill="x", pady=(8, 2))
        self.b_probar_web = ttk.Button(botones, text="Probar conexión", command=self.probar_web)
        self.b_probar_web.pack(side="left")
        ttk.Button(botones, text="Guardar", command=self.guardar_web).pack(side="left", padx=8)
        self.ind_web = self._indicador(botones, "Sin probar")
        self.ind_web.pack(side="left", padx=8)
        self.lbl_res_web = ttk.Label(der, text="", wraplength=560, justify="left")
        self.lbl_res_web.pack(anchor="w", pady=(2, 6))
        ttk.Separator(der).pack(fill="x", pady=4)
        ttk.Label(der, text=AYUDA_WEB, style="Gris.TLabel", wraplength=580,
                  justify="left").pack(anchor="w")

        self._tipo_web()
        self.refrescar_lista()

    def _mostrar_claves(self):
        show = "" if self.w_ver.get() else "•"
        for e in (self.e_pass, self.e_ck, self.e_cs):
            e.configure(show=show)

    def _tipo_web(self):
        if self.w_entrega.get() == "paquete":
            self.f_cred.grid_remove()
            self.f_woo.grid_remove()
            self.f_cat.grid_remove()
            self.lbl_paquete.grid()
            self.b_detectar.configure(state="disabled")
            return
        self.lbl_paquete.grid_remove()
        self.f_cred.grid()
        self.b_detectar.configure(state="normal")
        if self.w_tipo.get() == "woocommerce":
            self.f_cat.grid_remove()
            self.f_woo.grid()
        else:
            self.f_woo.grid_remove()
            self.f_cat.grid()

    def refrescar_lista(self, seleccionar=None):
        self.lista.delete(0, "end")
        for s in self.datos.get("sitios", []):
            self.lista.insert("end", s.get("nombre", "(sin nombre)"))
        if seleccionar is not None and 0 <= seleccionar < self.lista.size():
            self.lista.selection_set(seleccionar)
            self.web_idx = seleccionar
            self._cargar_form(self.datos["sitios"][seleccionar])
        elif self.lista.size() and self.web_idx is None:
            self.lista.selection_set(0)
            self.web_idx = 0
            self._cargar_form(self.datos["sitios"][0])

    def _elegir_en_lista(self):
        sel = self.lista.curselection()
        if not sel:
            return
        self.web_idx = sel[0]
        self._cargar_form(self.datos["sitios"][self.web_idx])

    def _cargar_form(self, s):
        self.w_nombre.set(s.get("nombre", ""))
        self.w_url.set(s.get("url", ""))
        self.w_tipo.set(s.get("tipo", "woocommerce"))
        self.w_entrega.set(s.get("entrega", "api"))
        self.w_usuario.set(s.get("wp_usuario", ""))
        self.w_pass.set(s.get("wp_app_password", ""))
        self.w_ck.set(s.get("wc_key", ""))
        self.w_cs.set(s.get("wc_secret", ""))
        self.w_post.set(s.get("post_type", ""))
        self._tipo_web()
        self.poner_estado(self.ind_web, "gris", "Sin probar")
        self.lbl_res_web.configure(text="")

    def nueva_web(self):
        self.lista.selection_clear(0, "end")
        self.web_idx = None
        self._cargar_form({})
        self.notebook.select(self.t_webs)

    def eliminar_web(self):
        if self.web_idx is None or self.web_idx >= len(self.datos["sitios"]):
            messagebox.showinfo("Eliminar", "Elegí primero una web de la lista.")
            return
        nombre = self.datos["sitios"][self.web_idx].get("nombre", "")
        if not messagebox.askyesno("Eliminar", f"¿Seguro que querés eliminar la web «{nombre}»?\n"
                                   "Solo se borra de este programa, no de internet."):
            return
        del self.datos["sitios"][self.web_idx]
        self.web_idx = None
        if self.guardar_datos():
            self.refrescar_lista()
            if not self.datos["sitios"]:
                self._cargar_form({})
            self.refrescar_sitios()

    def _leer_form(self) -> dict:
        url = normalizar_url(self.w_url.get())
        s = {"nombre": self.w_nombre.get().strip(), "url": url,
             "tipo": self.w_tipo.get(), "entrega": self.w_entrega.get()}
        if s["entrega"] == "paquete":
            return s
        s["wp_usuario"] = self.w_usuario.get().strip()
        s["wp_app_password"] = self.w_pass.get().strip()
        if s["tipo"] == "woocommerce":
            s["wc_key"] = self.w_ck.get().strip()
            s["wc_secret"] = self.w_cs.get().strip()
        else:
            s["post_type"] = self.w_post.get().split("—")[0].strip()
        return s

    def guardar_web(self):
        s = self._leer_form()
        if not s["nombre"] or not s["url"]:
            messagebox.showwarning("Faltan datos", "Escribí al menos el nombre y la URL de la web.")
            return
        self.w_url.set(s["url"])
        if s["entrega"] == "api" and "infinityfree" in s["url"].lower():
            if messagebox.askyesno(
                    "Hosting InfinityFree",
                    "Esta web parece estar en InfinityFree, que bloquea la API de WordPress.\n\n"
                    "¿Cambiar la entrega a «Paquete ZIP para el plugin»?"):
                self.w_entrega.set("paquete")
                self._tipo_web()
                s = self._leer_form()
        for i, x in enumerate(self.datos["sitios"]):
            if x.get("nombre") == s["nombre"] and i != self.web_idx:
                messagebox.showwarning("Nombre repetido", "Ya hay otra web con ese nombre.")
                return
        if self.web_idx is None:
            self.datos["sitios"].append(s)
            self.web_idx = len(self.datos["sitios"]) - 1
        else:
            self.datos["sitios"][self.web_idx] = s
        if not self.guardar_datos():
            return
        self.refrescar_lista(seleccionar=self.web_idx)
        self.refrescar_sitios()
        self.poner_estado(self.ind_web, "ok", "Guardado")

    def _cliente_wp(self, s):
        return ClienteWP(s["url"], s.get("wp_usuario", ""), s.get("wp_app_password", ""))

    def _probar_credenciales(self, s) -> str:
        info = self._cliente_wp(s).probar()
        modo = info.get("modo_rest", "wp-json")
        roles = ", ".join(info["roles"]) or "ninguno"
        msg = f"WordPress: conectado como {info['nombre']} (roles: {roles})."
        if s.get("tipo") == "woocommerce":
            ClienteWoo(s["url"], s.get("wc_key", ""), s.get("wc_secret", ""), modo_rest=modo).probar()
            msg += "\nWooCommerce: claves correctas."
        if modo == "rest_route":
            msg += "\nNota: este sitio responde por la ruta alternativa ?rest_route= (enlaces permanentes en modo simple)."
        if "administrator" not in info["roles"]:
            necesario = "Gerente de tienda" if s.get("tipo") == "woocommerce" else "Editor"
            msg += (f"\nAviso: este usuario no es administrador. Para subir productos "
                    f"alcanza con el rol {necesario}, pero si algo falla revisá el rol.")
        return msg

    def probar_web(self):
        s = self._leer_form()
        if not s["url"]:
            messagebox.showwarning("Falta la URL", "Escribí la URL de la web.")
            return
        if s["entrega"] == "paquete":
            messagebox.showinfo("Modo paquete", "En modo paquete no hace falta probar la conexión: "
                                "la app no se conecta a la web. Instalá el plugin y subí el ZIP.")
            return
        self.poner_estado(self.ind_web, "gris", "Probando…")
        self.lbl_res_web.configure(text="")
        self._hilo(lambda: self._probar_credenciales(s), self._fin_probar_web)

    def _fin_probar_web(self, res, err):
        if err:
            self.poner_estado(self.ind_web, "error", "Falló")
            self.lbl_res_web.configure(text=_msg_error(err), foreground=ROJO, wraplength=620)
            self._aviso_hosting(err, self.w_nombre.get().strip())
        else:
            self.poner_estado(self.ind_web, "ok", "Conectado")
            self.lbl_res_web.configure(text=res, foreground="")

    def _aviso_hosting(self, err, nombre_web=None) -> bool:
        """Si es el caso de hosting bloqueado, avisa y ofrece cambiar la web a modo paquete."""
        if isinstance(err, ErrorWeb) and MARCA_HOSTING in str(err):
            if messagebox.askyesno("Este hosting no permite la API",
                                   str(err) + "\n\n¿Cambiar esta web a «Paquete ZIP para el plugin»?"):
                self._cambiar_a_paquete(nombre_web)
            return True
        return False

    def _cambiar_a_paquete(self, nombre_web):
        self.w_entrega.set("paquete")
        self._tipo_web()
        for i, x in enumerate(self.datos["sitios"]):
            if nombre_web and x.get("nombre") == nombre_web:
                x["entrega"] = "paquete"
                self.guardar_datos()
                self.refrescar_sitios()
                if self.web_idx == i:
                    self._cargar_form(x)
                break

    def detectar_tipos(self):
        s = self._leer_form()
        if not s["url"]:
            messagebox.showwarning("Falta la URL", "Escribí la URL y las credenciales primero.")
            return
        self.b_detectar.configure(state="disabled")
        self._hilo(lambda: self._cliente_wp(s).tipos_contenido(), self._fin_detectar)

    def _fin_detectar(self, tipos, err):
        self.b_detectar.configure(state="normal")
        if err:
            self.lbl_res_web.configure(text=_msg_error(err), foreground=ROJO, wraplength=620)
            if not self._aviso_hosting(err):
                messagebox.showerror("Tipos de contenido", _msg_error(err))
            return
        if not tipos:
            messagebox.showinfo("Tipos de contenido",
                                "No se encontró ningún tipo. Puede que haga falta el mini-plugin "
                                "(ver README).")
            return
        self.c_post["values"] = [f"{t['rest_base']} — {t['nombre']}" for t in tipos]
        self.lbl_res_web.configure(
            text=f"Se encontraron {len(tipos)} tipos. Abrí la lista de Post type y elegí el del catálogo.",
            foreground="")

    def _elegir_post(self, _=None):
        self.w_post.set(self.w_post.get().split("—")[0].strip())

    # =====================================================================
    # Pestaña 3: Inteligencia artificial
    # =====================================================================
    def _seccion_ia(self, titulo, ayuda):
        marco = ttk.LabelFrame(self.t_ia, text=titulo, padding=8)
        marco.pack(fill="x", pady=(0, 8))
        marco.columnconfigure(1, weight=1)
        return marco

    def _fila_clave(self, marco, var, fila):
        ttk.Label(marco, text="Clave").grid(row=fila, column=0, sticky="w", pady=3)
        e = ttk.Entry(marco, textvariable=var, show="•")
        e.grid(row=fila, column=1, sticky="ew", pady=3)
        ver = tk.BooleanVar(value=False)
        ttk.Checkbutton(marco, text="Mostrar", variable=ver,
                        command=lambda: e.configure(show="" if ver.get() else "•")
                        ).grid(row=fila, column=2, padx=8)
        return e

    def _armar_ia(self):
        p = self.t_ia
        d = self.datos
        self.i_or = tk.StringVar(value=d.get("openrouter_api_key", ""))
        self.i_or_modelo = tk.StringVar(value=d.get("openrouter_modelo", "") or "openrouter/free")
        self.i_ge = tk.StringVar(value=d.get("gemini_api_key", ""))
        self.i_ge_modelo = tk.StringVar(value=d.get("gemini_modelo", "") or "gemini-3.5-flash-lite")
        self.i_sp = tk.StringVar(value=d.get("serpapi_key", ""))

        # OpenRouter
        m = self._seccion_ia("OpenRouter (principal, gratis con límite)", "")
        self._fila_clave(m, self.i_or, 0)
        ttk.Label(m, text="Modelo").grid(row=1, column=0, sticky="w", pady=3)
        modelos = list(MODELOS_OPENROUTER)
        if self.i_or_modelo.get() not in modelos:
            modelos.append(self.i_or_modelo.get())
        ttk.Combobox(m, textvariable=self.i_or_modelo, values=modelos).grid(
            row=1, column=1, sticky="ew", pady=3)
        fb = ttk.Frame(m)
        fb.grid(row=2, column=0, columnspan=3, sticky="w", pady=3)
        self.b_or = ttk.Button(fb, text="Probar", command=self.probar_or)
        self.b_or.pack(side="left")
        self.ind_or = self._indicador(fb, "Sin probar" if not d.get("openrouter_api_key") else "Clave guardada")
        self.ind_or.pack(side="left", padx=10)
        ttk.Label(m, text="Creá la clave en openrouter.ai → Keys. Los modelos :free dan 50 peticiones "
                  "al día sin créditos y 1.000 al día si cargás 10 dólares una vez.",
                  style="Gris.TLabel", wraplength=780, justify="left"
                  ).grid(row=3, column=0, columnspan=3, sticky="w")

        # Gemini
        m = self._seccion_ia("Gemini (respaldo)", "")
        self._fila_clave(m, self.i_ge, 0)
        ttk.Label(m, text="Modelo").grid(row=1, column=0, sticky="w", pady=3)
        modelos = list(MODELOS_GEMINI)
        if self.i_ge_modelo.get() not in modelos:
            modelos.append(self.i_ge_modelo.get())
        ttk.Combobox(m, textvariable=self.i_ge_modelo, values=modelos).grid(
            row=1, column=1, sticky="ew", pady=3)
        fb = ttk.Frame(m)
        fb.grid(row=2, column=0, columnspan=3, sticky="w", pady=3)
        self.b_ge = ttk.Button(fb, text="Probar", command=self.probar_ge)
        self.b_ge.pack(side="left")
        self.ind_ge = self._indicador(fb, "Sin probar" if not d.get("gemini_api_key") else "Clave guardada")
        self.ind_ge.pack(side="left", padx=10)
        ttk.Label(m, text="Creá la clave en aistudio.google.com → Get API key.",
                  style="Gris.TLabel").grid(row=3, column=0, columnspan=3, sticky="w")

        # SerpAPI
        m = self._seccion_ia("SerpAPI (opcional, para buscar fotos en Google Imágenes)", "")
        self._fila_clave(m, self.i_sp, 0)
        fb = ttk.Frame(m)
        fb.grid(row=1, column=0, columnspan=3, sticky="w", pady=3)
        self.b_sp = ttk.Button(fb, text="Probar", command=self.probar_sp)
        self.b_sp.pack(side="left")
        self.ind_sp = self._indicador(fb, "Sin probar" if not d.get("serpapi_key") else "Clave guardada")
        self.ind_sp.pack(side="left", padx=10)
        ttk.Label(m, text="250 búsquedas gratis al mes. Sin esta clave se usa DuckDuckGo, que es "
                  "gratis y no necesita clave.", style="Gris.TLabel", wraplength=780,
                  justify="left").grid(row=2, column=0, columnspan=3, sticky="w")

        m = self._seccion_ia("Fotos de internet", "")
        for i, (valor, texto) in enumerate(LICENCIAS):
            ttk.Radiobutton(m, text=texto, value=valor, variable=self.v_licencia,
                            command=self.guardar_opciones).grid(row=i, column=0, columnspan=3,
                                                                 sticky="w")
        ttk.Label(m, text="El filtro de licencia depende de lo que cada sitio declare; "
                  "no es una garantía legal.", style="Gris.TLabel", wraplength=780,
                  justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        pie = ttk.Frame(p)
        pie.pack(fill="x", pady=(4, 0))
        ttk.Button(pie, text="Guardar claves", style="Grande.TButton",
                   command=self.guardar_claves).pack(side="left")
        self.ind_guardado = self._indicador(pie, "Sin cambios")
        self.ind_guardado.pack(side="left", padx=12)
        ttk.Label(p, text="Las claves se guardan solo en tu computadora, en sitios.json.",
                  style="Gris.TLabel").pack(anchor="w", pady=(6, 0))

    def _probar_clave(self, boton, ind, funcion):
        self.poner_estado(ind, "gris", "Probando…")
        boton.configure(state="disabled")

        def listo(res, err):
            boton.configure(state="normal")
            if err:
                self.poner_estado(ind, "error", _msg_error(err))
            else:
                self.poner_estado(ind, "ok", res)
        self._hilo(funcion, listo)

    def probar_or(self):
        self._probar_clave(self.b_or, self.ind_or,
                           lambda c=self.i_or.get().strip(): ia.probar_openrouter(c))

    def probar_ge(self):
        self._probar_clave(self.b_ge, self.ind_ge,
                           lambda c=self.i_ge.get().strip(), m=self.i_ge_modelo.get().strip():
                           ia.probar_gemini(c, m))

    def probar_sp(self):
        self._probar_clave(self.b_sp, self.ind_sp,
                           lambda c=self.i_sp.get().strip(): ia.probar_serpapi(c))

    def guardar_claves(self):
        self.datos["openrouter_api_key"] = self.i_or.get().strip()
        self.datos["openrouter_modelo"] = self.i_or_modelo.get().strip() or "openrouter/free"
        self.datos["gemini_api_key"] = self.i_ge.get().strip()
        self.datos["gemini_modelo"] = self.i_ge_modelo.get().strip() or "gemini-3.5-flash-lite"
        self.datos["serpapi_key"] = self.i_sp.get().strip()
        if self.guardar_datos():
            self.refrescar_ia_disponible()
            self.poner_estado(self.ind_guardado, "ok", "Claves guardadas")

    # =====================================================================
    # Pestaña 4: Ayuda
    # =====================================================================
    def _armar_ayuda(self):
        p = self.t_ayuda
        for titulo, cuerpo in TEXTO_AYUDA:
            ttk.Label(p, text=titulo, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 0))
            ttk.Label(p, text=cuerpo, wraplength=820, justify="left").pack(anchor="w")
        fila = ttk.Frame(p)
        fila.pack(anchor="w", pady=(10, 4))
        ttk.Button(fila, text="Abrir carpeta del plugin",
                   command=lambda: os.startfile(CARPETA / "plugin")).pack(side="left")
        ttk.Label(fila, text="subidor-productos.zip se instala una vez por web (en multisitio: Mis "
                  "sitios → Administrador de la red → Plugins → Añadir nuevo)", wraplength=620,
                  justify="left").pack(side="left", padx=8)
        ttk.Label(p, text="Consejos para las fotos del cliente",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 0))
        ttk.Label(p, text=CONSEJOS_FOTOS, justify="left").pack(anchor="w")
        ttk.Button(p, text="Copiar guía para el cliente",
                   command=self._copiar_guia).pack(anchor="w", pady=(6, 0))
        self.l_guia = ttk.Label(p, text="")
        self.l_guia.pack(anchor="w")
        ttk.Button(p, text="Abrir carpeta del programa",
                   command=lambda: os.startfile(CARPETA)).pack(anchor="w", pady=12)

    def _copiar_guia(self):
        try:
            texto = GUIA_CLIENTE.read_text(encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Guía", f"No se pudo leer guia-fotos-para-clientes.txt: {e}")
            return
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.l_guia.configure(text="Guía copiada: pegala en WhatsApp para el cliente.")


if __name__ == "__main__":
    App().mainloop()
