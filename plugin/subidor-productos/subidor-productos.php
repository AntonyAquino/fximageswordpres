<?php
/**
 * Plugin Name: Subidor de productos
 * Description: Importa productos en borrador desde un paquete ZIP creado con la app Subidor de productos.
 * Version: 1.0.0
 * Author: Subidor de productos
 * Text Domain: subidor-productos
 * Requires PHP: 7.4
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/* ---------------------------------------------------------------------
 * Funciones auxiliares (sin depender de WordPress, fáciles de probar)
 * ------------------------------------------------------------------ */

/** True si el nombre de una entrada del ZIP es seguro (sin .., sin ruta absoluta). */
function subpro_ruta_segura( $nombre ) {
	$nombre = (string) $nombre;
	if ( '' === $nombre || false !== strpos( $nombre, "\0" ) ) {
		return false;
	}
	$n = str_replace( '\\', '/', $nombre );
	if ( '/' === $n[0] || preg_match( '#^[A-Za-z]:#', $n ) ) {
		return false;
	}
	foreach ( explode( '/', $n ) as $parte ) {
		if ( '..' === $parte ) {
			return false;
		}
	}
	return true;
}

/** Lee productos.csv y devuelve una lista de filas asociativas. */
function subpro_leer_csv( $ruta ) {
	$filas = array();
	$f     = @fopen( $ruta, 'r' );
	if ( ! $f ) {
		return $filas;
	}
	$cabecera = null;
	$primera  = true;
	while ( ( $r = fgetcsv( $f, 0, ',', '"', '' ) ) !== false ) {
		if ( $primera ) {
			$primera = false;
			if ( isset( $r[0] ) ) {
				$r[0] = preg_replace( '/^\xEF\xBB\xBF/', '', $r[0] );
			}
		}
		if ( null === $cabecera ) {
			$cabecera = array_map(
				function ( $c ) {
					return strtolower( trim( (string) $c ) );
				},
				$r
			);
			continue;
		}
		if ( 1 === count( $r ) && ( null === $r[0] || '' === trim( $r[0] ) ) ) {
			continue;
		}
		$fila = array();
		foreach ( array( 'nombre', 'fotos', 'categoria', 'descripcion', 'precio', 'clave' ) as $col ) {
			$i            = array_search( $col, $cabecera, true );
			$fila[ $col ] = ( false !== $i && isset( $r[ $i ] ) ) ? trim( (string) $r[ $i ] ) : '';
		}
		$filas[] = $fila;
	}
	fclose( $f );
	return $filas;
}

/** "Q 1,250.50" -> "1250.50"; vacío si no hay número. */
function subpro_limpiar_precio( $texto ) {
	$t = preg_replace( '/[^0-9.]/', '', str_replace( ',', '', (string) $texto ) );
	return is_numeric( $t ) ? $t : '';
}

/** Borra un directorio de forma recursiva, solo si está dentro de subpro-tmp. */
function subpro_borrar_dir( $dir ) {
	$dir = rtrim( str_replace( '\\', '/', $dir ), '/' );
	if ( false === strpos( $dir, '/subpro-tmp/' ) || ! is_dir( $dir ) ) {
		return;
	}
	$it = new RecursiveIteratorIterator(
		new RecursiveDirectoryIterator( $dir, FilesystemIterator::SKIP_DOTS ),
		RecursiveIteratorIterator::CHILD_FIRST
	);
	foreach ( $it as $x ) {
		if ( $x->isDir() && ! $x->isLink() ) {
			@rmdir( $x->getPathname() );
		} else {
			@unlink( $x->getPathname() );
		}
	}
	@rmdir( $dir );
}

/* ---------------------------------------------------------------------
 * Menú
 * ------------------------------------------------------------------ */

add_action( 'admin_menu', 'subpro_menu' );
function subpro_menu() {
	add_management_page(
		'Subidor de productos',
		'Subidor de productos',
		'upload_files',
		'subidor-productos',
		'subpro_pagina'
	);
}

function subpro_post_types() {
	$tipos = get_post_types( array( 'public' => true ), 'objects' );
	unset( $tipos['attachment'] );
	return $tipos;
}

function subpro_pagina() {
	if ( ! current_user_can( 'upload_files' ) || ! current_user_can( 'edit_posts' ) ) {
		wp_die( esc_html( 'No tenés permiso para usar esta página.' ) );
	}
	$resultado = null;
	$error     = '';
	if ( 'POST' === $_SERVER['REQUEST_METHOD'] && isset( $_POST['subpro_enviar'] ) ) {
		check_admin_referer( 'subpro_importar', 'subpro_nonce' );
		$r = subpro_procesar_envio();
		if ( is_wp_error( $r ) ) {
			$error = $r->get_error_message();
		} else {
			$resultado = $r;
		}
	}

	$woo    = class_exists( 'WooCommerce' );
	$tipos  = subpro_post_types();
	$guard  = get_option( 'subpro_post_type', '' );
	$limite = round( wp_max_upload_size() / 1048576, 1 );

	echo '<div class="wrap"><h1>Subidor de productos</h1>';

	if ( $error ) {
		echo '<div class="notice notice-error"><p>' . esc_html( $error ) . '</p></div>';
	}
	if ( $resultado ) {
		subpro_mostrar_resultado( $resultado );
	}

	echo '<p>Subí el paquete ZIP que creó la app. Los productos se crean como <strong>borrador</strong>.</p>';
	echo '<form method="post" enctype="multipart/form-data">';
	wp_nonce_field( 'subpro_importar', 'subpro_nonce' );
	echo '<table class="form-table" role="presentation"><tbody>';
	echo '<tr><th scope="row"><label for="subpro_zip">Paquete ZIP</label></th><td>';
	echo '<input type="file" name="subpro_zip" id="subpro_zip" accept=".zip" required>';
	echo '<p class="description">Límite de subida del servidor: ' . esc_html( $limite ) . ' MB. ';
	echo 'Si el paquete pesa más, la app lo parte en varios ZIP; subilos uno por uno.</p>';
	echo '</td></tr>';

	echo '<tr><th scope="row"><label for="subpro_tipo">Tipo de contenido para los productos</label></th><td>';
	echo '<select name="subpro_tipo" id="subpro_tipo">';
	foreach ( $tipos as $slug => $obj ) {
		$sel = '';
		if ( $guard ? ( $guard === $slug ) : ( $woo && 'product' === $slug ) ) {
			$sel = ' selected';
		}
		echo '<option value="' . esc_attr( $slug ) . '"' . $sel . '>' . esc_html( $obj->labels->name . ' (' . $slug . ')' ) . '</option>';
	}
	echo '</select>';
	if ( $woo ) {
		echo '<p class="description">WooCommerce está activo: si elegís «product», se crean productos simples de la tienda.</p>';
	}
	echo '</td></tr>';

	echo '<tr><th scope="row">Opciones</th><td><label>';
	echo '<input type="checkbox" name="subpro_omitir" value="1" checked> Omitir productos que ya existan con el mismo nombre';
	echo '</label></td></tr>';
	echo '</tbody></table>';
	echo '<p class="submit"><button type="submit" name="subpro_enviar" value="1" class="button button-primary">Importar paquete</button></p>';
	echo '</form></div>';
}

function subpro_mostrar_resultado( $res ) {
	$c = 0;
	$o = 0;
	$e = 0;
	foreach ( $res as $fila ) {
		if ( 'creado' === $fila['estado'] ) {
			$c++;
		} elseif ( 'ya existía' === $fila['estado'] ) {
			$o++;
		} else {
			$e++;
		}
	}
	echo '<div class="notice notice-info"><p><strong>Creados: ' . (int) $c . ' · Omitidos: ' . (int) $o . ' · Errores: ' . (int) $e . '</strong></p></div>';
	echo '<table class="widefat striped" style="max-width:900px;margin-bottom:20px"><thead><tr>';
	echo '<th>Producto</th><th>Estado</th><th>Fotos subidas</th><th></th></tr></thead><tbody>';
	foreach ( $res as $fila ) {
		echo '<tr><td>' . esc_html( $fila['nombre'] ) . '</td>';
		echo '<td>' . esc_html( $fila['estado'] );
		if ( ! empty( $fila['nota'] ) ) {
			echo '<br><small>' . esc_html( $fila['nota'] ) . '</small>';
		}
		echo '</td><td>' . (int) $fila['fotos'] . '</td><td>';
		if ( ! empty( $fila['id'] ) ) {
			$link = get_edit_post_link( (int) $fila['id'], 'raw' );
			if ( $link ) {
				echo '<a href="' . esc_url( $link ) . '">Editar</a>';
			}
		}
		echo '</td></tr>';
	}
	echo '</tbody></table>';
}

/* ---------------------------------------------------------------------
 * Importación
 * ------------------------------------------------------------------ */

function subpro_procesar_envio() {
	@set_time_limit( 300 );

	if ( ! current_user_can( 'upload_files' ) || ! current_user_can( 'edit_posts' ) ) {
		return new WP_Error( 'permiso', 'No tenés permiso para importar productos.' );
	}
	if ( ! class_exists( 'ZipArchive' ) ) {
		return new WP_Error( 'zip', 'Este servidor no tiene la extensión ZipArchive de PHP, así que no puede abrir paquetes ZIP.' );
	}
	if ( empty( $_FILES['subpro_zip'] ) || ! isset( $_FILES['subpro_zip']['error'] ) ) {
		return new WP_Error( 'archivo', 'No se recibió ningún archivo.' );
	}
	$f = $_FILES['subpro_zip'];
	if ( UPLOAD_ERR_OK !== (int) $f['error'] ) {
		return new WP_Error( 'archivo', 'La subida del archivo falló (código ' . (int) $f['error'] . '). Revisá que no pase del límite del servidor.' );
	}
	if ( ! is_uploaded_file( $f['tmp_name'] ) ) {
		return new WP_Error( 'archivo', 'Archivo de subida no válido.' );
	}

	$tipo_post = isset( $_POST['subpro_tipo'] ) ? sanitize_key( wp_unslash( $_POST['subpro_tipo'] ) ) : '';
	$validos   = subpro_post_types();
	if ( ! isset( $validos[ $tipo_post ] ) ) {
		$tipo_post = class_exists( 'WooCommerce' ) ? 'product' : 'post';
	}
	update_option( 'subpro_post_type', $tipo_post );
	$omitir = ! empty( $_POST['subpro_omitir'] );

	$subidas = wp_upload_dir();
	if ( ! empty( $subidas['error'] ) ) {
		return new WP_Error( 'dir', 'No se puede escribir en la carpeta de subidas: ' . $subidas['error'] );
	}
	$dir = rtrim( $subidas['basedir'], '/\\' ) . '/subpro-tmp/' . uniqid( 'p', true ) . '/';
	if ( ! wp_mkdir_p( $dir ) ) {
		return new WP_Error( 'dir', 'No se pudo crear la carpeta temporal.' );
	}
	$zip_ruta = $dir . 'paquete.zip';
	if ( ! @move_uploaded_file( $f['tmp_name'], $zip_ruta ) ) {
		subpro_borrar_dir( $dir );
		return new WP_Error( 'dir', 'No se pudo guardar el ZIP en la carpeta temporal.' );
	}

	$res = subpro_importar_zip( $zip_ruta, $dir, $tipo_post, $omitir );
	subpro_borrar_dir( $dir );
	return $res;
}

function subpro_importar_zip( $zip_ruta, $dir, $tipo_post, $omitir ) {
	$zip = new ZipArchive();
	if ( true !== $zip->open( $zip_ruta ) ) {
		return new WP_Error( 'zip', 'No se pudo abrir el ZIP. ¿Está dañado?' );
	}
	$ext_dir = $dir . 'x/';
	wp_mkdir_p( $ext_dir );
	$tiene_csv = false;
	for ( $i = 0; $i < $zip->numFiles; $i++ ) {
		$nom = $zip->getNameIndex( $i );
		if ( ! subpro_ruta_segura( $nom ) ) {
			$zip->close();
			return new WP_Error( 'zip', 'El ZIP contiene rutas no permitidas; se rechazó.' );
		}
		if ( 'productos.csv' === $nom ) {
			$tiene_csv = true;
		}
	}
	if ( ! $tiene_csv ) {
		$zip->close();
		return new WP_Error( 'zip', 'El ZIP no trae productos.csv. ¿Es un paquete de la app?' );
	}
	// Extraer solo productos.csv y fotos permitidas, una por una (nada se ejecuta).
	$ok_ext = array( 'jpg', 'jpeg', 'png', 'webp' );
	for ( $i = 0; $i < $zip->numFiles; $i++ ) {
		$nom = str_replace( '\\', '/', $zip->getNameIndex( $i ) );
		if ( '/' === substr( $nom, -1 ) ) {
			continue;
		}
		$ext = strtolower( pathinfo( $nom, PATHINFO_EXTENSION ) );
		if ( 'productos.csv' !== $nom && ! ( 0 === strpos( $nom, 'fotos/' ) && in_array( $ext, $ok_ext, true ) ) ) {
			continue;
		}
		$destino = $ext_dir . $nom;
		wp_mkdir_p( dirname( $destino ) );
		$in = $zip->getStream( $zip->getNameIndex( $i ) );
		if ( ! $in ) {
			continue;
		}
		$out = fopen( $destino, 'wb' );
		if ( $out ) {
			stream_copy_to_stream( $in, $out );
			fclose( $out );
		}
		fclose( $in );
	}
	$zip->close();

	$filas = subpro_leer_csv( $ext_dir . 'productos.csv' );
	if ( ! $filas ) {
		return new WP_Error( 'csv', 'productos.csv está vacío o no se pudo leer.' );
	}

	require_once ABSPATH . 'wp-admin/includes/image.php';
	require_once ABSPATH . 'wp-admin/includes/file.php';
	$filtro_mimes = function ( $m ) {
		$m['webp'] = 'image/webp';
		return $m;
	};
	add_filter( 'upload_mimes', $filtro_mimes );

	$resultado = array();
	foreach ( $filas as $fila ) {
		$resultado[] = subpro_importar_fila( $fila, $ext_dir, $tipo_post, $omitir );
	}

	remove_filter( 'upload_mimes', $filtro_mimes );
	return $resultado;
}

function subpro_buscar_existente( $nombre, $clave, $tipo ) {
	global $wpdb;
	$tipos = array_values( array_unique( array( $tipo, 'product' ) ) );
	$ph    = implode( ',', array_fill( 0, count( $tipos ), '%s' ) );
	$args  = array_merge( $tipos, array( $nombre ) );
	$id    = $wpdb->get_var(
		$wpdb->prepare(
			"SELECT ID FROM {$wpdb->posts} WHERE post_type IN ($ph) AND post_title = %s AND post_status <> 'trash' LIMIT 1", // phpcs:ignore
			$args
		)
	);
	if ( $id ) {
		return (int) $id;
	}
	if ( '' !== $clave ) {
		$id = $wpdb->get_var(
			$wpdb->prepare(
				"SELECT p.ID FROM {$wpdb->posts} p INNER JOIN {$wpdb->postmeta} m ON m.post_id = p.ID WHERE m.meta_key = '_subpro_clave' AND m.meta_value = %s AND p.post_status <> 'trash' LIMIT 1",
				$clave
			)
		);
		if ( $id ) {
			return (int) $id;
		}
	}
	return 0;
}

function subpro_subir_foto( $ruta, $nombre_prod ) {
	if ( ! is_file( $ruta ) ) {
		return new WP_Error( 'foto', 'no existe la foto ' . basename( $ruta ) );
	}
	$ext = strtolower( pathinfo( $ruta, PATHINFO_EXTENSION ) );
	if ( ! in_array( $ext, array( 'jpg', 'jpeg', 'png', 'webp' ), true ) || false === @getimagesize( $ruta ) ) {
		return new WP_Error( 'foto', basename( $ruta ) . ' no es una imagen válida' );
	}
	$bits = wp_upload_bits( basename( $ruta ), null, file_get_contents( $ruta ) );
	if ( ! empty( $bits['error'] ) ) {
		return new WP_Error( 'foto', 'no se pudo guardar ' . basename( $ruta ) . ': ' . $bits['error'] );
	}
	$tipo = wp_check_filetype( $bits['file'] );
	if ( empty( $tipo['type'] ) ) {
		@unlink( $bits['file'] );
		return new WP_Error( 'foto', 'el servidor no acepta el formato de ' . basename( $ruta ) );
	}
	$id = wp_insert_attachment(
		array(
			'post_mime_type' => $tipo['type'],
			'post_title'     => $nombre_prod,
			'post_content'   => '',
			'post_status'    => 'inherit',
		),
		$bits['file']
	);
	if ( is_wp_error( $id ) || ! $id ) {
		return new WP_Error( 'foto', 'no se pudo registrar ' . basename( $ruta ) );
	}
	wp_update_attachment_metadata( $id, wp_generate_attachment_metadata( $id, $bits['file'] ) );
	update_post_meta( $id, '_wp_attachment_image_alt', $nombre_prod );
	return (int) $id;
}

function subpro_asignar_categoria( $post_id, $tipo, $nombre_cat ) {
	$taxs = get_object_taxonomies( $tipo, 'objects' );
	foreach ( $taxs as $tax ) {
		if ( $tax->public && $tax->hierarchical ) {
			$t = term_exists( $nombre_cat, $tax->name );
			if ( ! $t ) {
				$t = wp_insert_term( $nombre_cat, $tax->name );
			}
			if ( ! is_wp_error( $t ) ) {
				$tid = is_array( $t ) ? (int) $t['term_id'] : (int) $t;
				wp_set_object_terms( $post_id, array( $tid ), $tax->name );
			}
			return;
		}
	}
}

function subpro_importar_fila( $fila, $ext_dir, $tipo_post, $omitir ) {
	$nombre = $fila['nombre'];
	$salida = array(
		'nombre' => $nombre,
		'estado' => 'error',
		'fotos'  => 0,
		'id'     => 0,
		'nota'   => '',
	);
	if ( '' === $nombre ) {
		$salida['nota'] = 'fila sin nombre';
		return $salida;
	}
	$clave = $fila['clave'];

	if ( $omitir ) {
		$existe = subpro_buscar_existente( $nombre, $clave, $tipo_post );
		if ( $existe ) {
			$salida['estado'] = 'ya existía';
			$salida['id']     = $existe;
			return $salida;
		}
	}

	$notas = array();
	$ids   = array();
	foreach ( array_filter( array_map( 'trim', explode( ';', $fila['fotos'] ) ) ) as $foto ) {
		if ( ! subpro_ruta_segura( $foto ) ) {
			$notas[] = 'foto con ruta no permitida';
			continue;
		}
		$r = subpro_subir_foto( $ext_dir . 'fotos/' . basename( $foto ), $nombre );
		if ( is_wp_error( $r ) ) {
			$notas[] = $r->get_error_message();
		} else {
			$ids[] = $r;
		}
	}
	$salida['fotos'] = count( $ids );

	$post_id = 0;
	try {
		if ( class_exists( 'WooCommerce' ) && class_exists( 'WC_Product_Simple' ) && 'product' === $tipo_post ) {
			$p = new WC_Product_Simple();
			$p->set_name( $nombre );
			$p->set_status( 'draft' );
			if ( $ids ) {
				$p->set_image_id( $ids[0] );
				$p->set_gallery_image_ids( array_slice( $ids, 1 ) );
			}
			$precio = subpro_limpiar_precio( $fila['precio'] );
			if ( '' !== $precio ) {
				$p->set_regular_price( $precio );
			}
			if ( '' !== $fila['descripcion'] ) {
				$p->set_description( $fila['descripcion'] );
			}
			if ( '' !== $fila['categoria'] ) {
				$t = term_exists( $fila['categoria'], 'product_cat' );
				if ( ! $t ) {
					$t = wp_insert_term( $fila['categoria'], 'product_cat' );
				}
				if ( ! is_wp_error( $t ) ) {
					$p->set_category_ids( array( is_array( $t ) ? (int) $t['term_id'] : (int) $t ) );
				}
			}
			$post_id = $p->save();
		} else {
			$contenido = '';
			if ( '' !== $fila['descripcion'] ) {
				$contenido .= '<!-- wp:paragraph --><p>' . esc_html( $fila['descripcion'] ) . "</p><!-- /wp:paragraph -->\n";
			}
			foreach ( array_slice( $ids, 1 ) as $aid ) {
				$url        = wp_get_attachment_url( $aid );
				$contenido .= sprintf(
					'<!-- wp:image {"id":%1$d,"sizeSlug":"large"} --><figure class="wp-block-image size-large"><img src="%2$s" alt="%3$s" class="wp-image-%1$d"/></figure><!-- /wp:image -->' . "\n",
					$aid,
					esc_url( $url ),
					esc_attr( $nombre )
				);
			}
			$post_id = wp_insert_post(
				array(
					'post_type'    => $tipo_post,
					'post_status'  => 'draft',
					'post_title'   => $nombre,
					'post_content' => $contenido,
				),
				true
			);
			if ( is_wp_error( $post_id ) ) {
				throw new Exception( $post_id->get_error_message() );
			}
			if ( $ids ) {
				set_post_thumbnail( $post_id, $ids[0] );
			}
			if ( '' !== $fila['categoria'] ) {
				subpro_asignar_categoria( $post_id, $tipo_post, $fila['categoria'] );
			}
		}
	} catch ( Exception $e ) {
		$notas[]        = 'no se pudo crear: ' . $e->getMessage();
		$salida['nota'] = implode( '; ', $notas );
		return $salida;
	}

	if ( ! $post_id ) {
		$notas[]        = 'no se pudo crear el producto';
		$salida['nota'] = implode( '; ', $notas );
		return $salida;
	}
	update_post_meta( $post_id, '_subpro_clave', $clave );
	$salida['estado'] = 'creado';
	$salida['id']     = (int) $post_id;
	$salida['nota']   = implode( '; ', $notas );
	return $salida;
}
