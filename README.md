# Subidor de productos

## Qué hace

Usted pone en una carpeta las fotos que manda el cliente y una hoja `productos.xlsx`. El programa convierte las fotos a WebP, las sube a la biblioteca de medios de la web y crea cada producto como **borrador** con su nombre y sus fotos. Después usted solo revisa y publica desde el panel de la web.

Funciona con tiendas WooCommerce y con catálogos hechos con un plugin de catálogo (tipo de contenido propio, por ejemplo `al_product`).

Opcional:
- Si una fila no tiene nombre, una IA lo sugiere viendo la primera foto (OpenRouter primero, Gemini de respaldo).
- Arregla solas las fotos feas del cliente (luz, contraste, nitidez) y les quita el fondo para dejarlo blanco, tipo catálogo.
- Busca fotos en internet (DuckDuckGo, y SerpAPI si tiene clave) y la IA elige las mejores entre las del cliente y las de internet.

## Instalar

1. Haga doble clic en `instalar.bat`. Crea una carpeta `.venv` e instala todo ahí (no toca el resto de la compu).
2. Para abrir el programa, doble clic en `abrir.bat`.
3. Todo lo demás se configura desde la ventana: pestaña **Webs** (sus sitios) y pestaña **Inteligencia artificial** (claves). No hace falta abrir ningún archivo.

La primera vez que se quita un fondo, el programa descarga un modelo de unos 170 MB (u2net) a la carpeta `.rembg` de su usuario. Hace falta internet solo esa vez; después funciona sin conexión. Si falta `rembg`, la casilla aparece deshabilitada con el aviso "ejecutá instalar.bat".

Nota: si `pillow-heif` no se pudiera instalar, el programa sigue funcionando; solo no podría leer fotos HEIC de iPhone.

## La ventana

- **Subir productos**: 4 pasos numerados. 1) elegir la web, 2) elegir la carpeta con fotos y hoja (muestra cuántas fotos y productos hay, y puede crear la hoja), 3) opciones de IA y fotos, 4) subir, con barra de progreso.
- **Webs**: agregar, editar, probar y eliminar sitios.
- **Inteligencia artificial**: claves de OpenRouter, Gemini y SerpAPI, cada una con botón "Probar".
- **Ayuda**: resumen del flujo y de los estados.

Los datos se guardan en `sitios.json`, un archivo que existe solo en esta computadora (ya está en `.gitignore`). Lo crea el programa solo; no hay que editarlo a mano ni compartirlo, porque contiene claves.

## Configurar cada web (pestaña Webs)

Presione **Nueva web**, llene el formulario, use **Probar conexión** y luego **Guardar**.

### Contraseña de aplicación (todas las webs)
1. Entre al panel de la web con el usuario que va a usar.
2. Vaya a **Usuarios → Perfil**.
3. Baje a **Contraseñas de aplicación**, escriba un nombre (por ejemplo "Subidor") y presione "Añadir nueva contraseña de aplicación".
4. Copie la contraseña que aparece (formato `xxxx xxxx xxxx xxxx xxxx xxxx`) en el campo "Contraseña de aplicación". Solo se muestra una vez.

### Claves REST de WooCommerce (solo tiendas)
1. Vaya a **WooCommerce → Ajustes → Avanzado → REST API → Añadir clave**.
2. Descripción: "Subidor". Usuario: el mismo. Permisos: **Lectura/Escritura**.
3. Copie la Clave de cliente (`ck_...`) en "Clave" y la Clave secreta (`cs_...`) en "Secreto".

### Catálogos
En vez de claves de WooCommerce se usa el **Post type**. Ver la siguiente sección.

## Cómo descubrir el post type del plugin de catálogo

- Opción fácil: en la pestaña Webs, con el tipo "Catálogo", presione **Detectar…** (después de poner URL, usuario y contraseña). Se llena la lista del campo Post type; elija la que corresponda y presione Guardar.
- Opción manual: en el panel, entre a "Añadir nuevo" producto del catálogo y mire la URL: aparece `post-new.php?post_type=XXXX`. Ese `XXXX` es el post type. Con la REST API se usa el `rest_base`, que casi siempre es igual.

### Si el plugin no aparece en la lista (mini-plugin)
Algunos plugins de catálogo no exponen su tipo de contenido en la REST API. En ese caso cree el archivo `wp-content/mu-plugins/rest-catalogo.php` en la web (si la carpeta `mu-plugins` no existe, créela) con este código, cambiando `al_product` por su post type:

```php
<?php
/*
Plugin Name: REST para catalogo
*/
add_filter('register_post_type_args', function ($args, $post_type) {
    if ($post_type === 'al_product') {
        $args['show_in_rest'] = true;
        $args['rest_base'] = 'al_product';
    }
    return $args;
}, 10, 2);
```

Después vuelva a presionar "Detectar…".

## Roles del usuario

- **Tiendas WooCommerce**: el usuario debe ser **Gerente de tienda** (o Administrador). Un Editor no puede crear ni editar productos.
- **Catálogos**: normalmente basta con **Editor**.

## Entrega por paquete ZIP (InfinityFree y hostings que bloquean la API)

Hay dos formas de entrega por web (campo **Entrega** en la pestaña Webs):
- **Subir por API**: lo de siempre (necesita usuario y contraseña de aplicación).
- **Paquete ZIP para el plugin**: no se piden claves. La app hace el mismo proceso (nombres, búsqueda y elección de fotos, arreglo, WebP) pero en vez de subir crea uno o varios ZIP en la carpeta de trabajo: `productos-<web>-<AAAAMMDD-HHMM>.zip` (el plugin no depende del nombre; este ZIP es el paquete de productos y se sube en Herramientas → Subidor de productos; el plugin es `plugin\subidor-productos.zip`, otro archivo que se instala una sola vez). Dentro van `productos.csv` y la carpeta `fotos/`. Si el total pasa de `max_zip_mb` (8 por defecto, en `opciones` de `sitios.json`) se parte en `-parte1`, `-parte2`, cada uno con su propio `productos.csv`. En la hoja las filas quedan `empaquetado` (y no se repiten); `enlace_edicion` dice el ZIP.

Si la URL contiene `infinityfree`, o la prueba de conexión detecta el hosting bloqueado, la app ofrece cambiar la web a paquete.

### Instalar el plugin (una sola vez por web)
1. Ejecute `empaquetar_plugin.py` si no existe `plugin\subidor-productos.zip` (ya viene creado).
2. En el panel de WordPress: **Plugins → Añadir nuevo → Subir plugin**, elija `plugin\subidor-productos.zip`, instale y active.
3. Cada vez que tenga un paquete: **Herramientas → Subidor de productos**, suba el ZIP (si hay varios, uno por uno). Los productos se crean en borrador y aparece una tabla con lo creado, omitido o con error. Si se corta el proceso, vuelva a subir el mismo ZIP: omite los que ya existen (por nombre o por la clave del paquete).
4. El plugin usa WooCommerce si está activo; si no, crea entradas del tipo de contenido que elija en el desplegable. Límite: el que tenga el servidor para subidas (lo muestra la misma página).

## Cómo llenar productos.xlsx

**Camino corto: solo fotos.** Ponga las fotos en una carpeta y presione Subir. Si no hay `productos.xlsx`, el programa lo crea solo con una fila por foto (`nombre` vacío, `fotos` = nombre del archivo) y, con la IA activa, sugiere el nombre de cada una. También puede usar el botón "Crear hoja en esta carpeta" para armarla antes y editarla. La hoja es opcional: sirve para poner nombres, precios y categorías, o para juntar varias fotos de un mismo producto en la columna `fotos` separadas por `;`.

Use `plantilla.xlsx` como base (si la pierde, ejecute `crear_plantilla.py`). Fila 1 = encabezados; no importan mayúsculas ni tildes.

| Columna | Para qué |
|---|---|
| `nombre` | Nombre del producto |
| `fotos` | Nombres de archivo separados por `;` (o `,`), dentro de la misma carpeta. Ejemplo: `silla1.jpg; silla2.jpg` |
| `categoria` | Solo tiendas. Si no existe, se crea |
| `descripcion` | Texto opcional |
| `precio` | Solo tiendas. Ejemplo: `250` |
| `estado`, `id`, `enlace_edicion`, `nota` | Las llena el programa (si faltan, las agrega al final) |

Qué pasa si falta algo:
- **Sin nombre y con fotos**: si está marcada la casilla de IA, se sugiere un nombre y queda anotado en `nota`. Si no, la fila queda `pendiente`.
- **Sin fotos y con nombre**: según el modo de fotos (ver abajo), se buscan en internet. Si no se encuentra nada, queda `pendiente`.
- **Sin nombre ni fotos**: `pendiente`.
- **Falta alguna foto de la lista**: se anota y se sigue con las que sí existen.

Las fotos convertidas quedan en la subcarpeta `convertidas`. Las bajadas de internet, en `internet` (con un archivo `fuentes.txt`: `archivo | dirección de la imagen | pasó el filtro de licencia sí/no`).

## Inteligencia artificial y fotos (pestaña Inteligencia artificial)

Pegue cada clave, presione **Probar** y luego **Guardar claves**.

- **OpenRouter** (principal): clave en openrouter.ai → Keys. Los modelos `:free` dan 50 peticiones al día sin créditos y 1.000 al día si carga 10 dólares una vez.
- **Gemini** (respaldo): clave en aistudio.google.com → Get API key.
- **SerpAPI** (opcional): 250 búsquedas gratis al mes para buscar en Google Imágenes. Sin clave se usa DuckDuckGo, que es gratis.

Opciones en el paso 3 de la pestaña Subir productos (se recuerdan):
- *Sugerir nombre con IA* cuando la fila no tiene nombre.
- *Elegir las mejores fotos con IA*: se descargan hasta 12 candidatas de internet (se descartan las menores de 600 px, GIF y repetidas). La IA recibe hasta 8 miniaturas (primero las del cliente ya arregladas, luego las de internet) y elige las mejores. Prefiere fotos reales del producto exacto y mantiene la del cliente si es aceptable. Si la IA falla o no elige, se usan las del cliente más hasta 2 de internet por tamaño.
- *Máximo de fotos por producto* (por defecto 4).

### Modo de fotos (de dónde salen)
- **Solo las del cliente**: no se busca nada en internet.
- **Internet primero (recomendado, por defecto)**: siempre se busca en internet y la IA prefiere fotos de catálogo del producto exacto; usa las del cliente solo si no hay buenas de internet o el producto es artesanal o sin marca. Se descartan fotos con marca de agua, logos de tiendas, texto, collages o de otra presentación, y se filtran de entrada las URL de bancos de imágenes (shutterstock, alamy, etc.). Migración única: si falta la marca `migrado_internet_primero`, el modo pasa a este.
- **Cliente e internet** (fotos del cliente primero; internet para completar): mantiene las del cliente si son aceptables; siempre se busca en internet y se eligen las mejores entre las dos fuentes. Las fotos del cliente que no se eligen no se borran; solo no se suben. La nota de la hoja dice, por ejemplo, "fotos: 2 del cliente + 2 de internet".
- **Internet solo si faltan**: se busca únicamente cuando la fila no tiene fotos.

### Guía de fotos para el cliente
La pestaña Ayuda trae consejos de fotos y el botón *Copiar guía para el cliente*, que copia al portapapeles `guia-fotos-para-clientes.txt` (redactado para reenviar por WhatsApp). Las fotos de vitrina (reflejos, suciedad) no quedan profesionales ni quitando el fondo; por eso, para productos de marca conviene Internet primero.

### Licencias de las fotos de internet (pestaña Inteligencia artificial)
- **Solo fotos de libre uso**: usa el filtro de uso comercial del buscador. Si no hay resultados, no usa internet y lo anota ("no se encontraron fotos de libre uso").
- **Libre uso primero (recomendado)**: igual, pero si no hay resultados busca sin filtro y la nota dice "fotos sin licencia confirmada, reemplazar por fotos del cliente".
- **Cualquier foto**: sin filtro; la nota dice "fotos de internet, revisar derechos de autor".

**Aviso:** el filtro de licencia depende de lo que cada sitio declare; no es una garantía legal. Revise las fotos de internet antes de publicar.

### Arreglo automático de fotos
- *Arreglar fotos del cliente*: corrige luz, contraste, balance de blancos y nitidez. Las fotos de internet solo reciben este arreglo.
- *Quitar el fondo y ponerlo blanco*: solo para fotos del cliente; deja el producto centrado sobre un cuadrado blanco. Si no se puede (por ejemplo, falta la librería), sigue sin quitarlo y la nota dice "no se pudo quitar el fondo".
- *Vista previa de una foto…* muestra el antes y el después de una foto y permite guardarla.
- Si una foto quedó mal: reemplácela en el panel de la web (Medios / editar el producto), o desmarque las casillas y vuelva a subir ese producto.

Si no hay ninguna clave de IA, las opciones de IA aparecen deshabilitadas (el arreglo de fotos y el modo de fotos siguen funcionando).

## Qué significa cada estado

- `subido`: el producto se creó como borrador. En la próxima corrida se salta.
- `empaquetado`: el producto quedó dentro de un ZIP para el plugin. También se salta.
- `pendiente`: faltó nombre o fotos; complete la fila y vuelva a subir.
- `error`: algo falló; vea la `nota`. Corrija y deje `estado` en blanco para reintentar.
- (vacío): todavía no se procesa.

## Problemas comunes

- **WebP rechazado**: algunos hostings no aceptan WebP. El programa lo detecta, sube JPG y lo anota en `nota`.
- **Error 401**: usuario o contraseña de aplicación incorrectos. Genere otra contraseña de aplicación, sin espacios de más.
- **Error 403**: falta de permisos (revise el rol) o el hosting/seguridad (por ejemplo Wordfence) bloquea la REST API. Pida que permitan su IP o la REST API.
- **404 al crear en un catálogo**: el post type no está expuesto en REST; use el mini-plugin de arriba.
- **El Excel no se guarda**: tenía `productos.xlsx` abierto. Cierre Excel; mientras tanto el programa guarda una copia en `productos_resultado.xlsx`.
- **Hosting gratuito (InfinityFree y similares)**: estos hostings bloquean con un reto de JavaScript a cualquier programa que no sea un navegador, y la app no puede usar la API de WordPress ahí (aparece "Este hosting no permite la API"). Alternativas: mover la web a un hosting que permita la API, o subir los productos a mano desde el panel de WordPress.
- **Enlaces permanentes en modo simple**: si `/wp-json/` da 404, la app prueba sola la ruta alternativa `/?rest_route=`. Si tampoco funciona, en WordPress vaya a Ajustes > Enlaces permanentes y elija cualquier opción que no sea "Simple".
- **URL con /wp-admin**: la app la limpia sola; basta la dirección principal (https://mitienda.com).
- **Registro**: todo queda en `registro.log`, en la carpeta del programa.
