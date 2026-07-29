# -*- coding: utf-8 -*-
"""
interfaz_comun.py — piezas compartidas entre la web (app.py) y la app de
escritorio del encargado (app_encargado.py): login, sesion, y el flujo de
"Nueva solicitud" que usan ambos roles.
"""

import base64
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import core
import formato_impresion

CARPETA_PDF = Path("formularios")
CARPETA_PDF.mkdir(exist_ok=True)

# app_encargado.py la pone en True después de importar este módulo. En modo
# escritorio, la app corre dentro de una ventana nativa (pywebview) en vez de
# un navegador real: ahí el botón de descarga y el truco de blob+window.open
# para "Imprimir" no tienen dónde aterrizar (no hay barra de descargas ni
# pestañas), así que en vez de fingir ser un navegador se abre el PDF ya
# generado con el visor que Windows tenga asociado — desde ahí el propio
# visor ofrece Guardar como e Imprimir de forma nativa.
MODO_ESCRITORIO = False

LOGO_CLARO = Path("logo_traiguen.png")          # azul, para fondo blanco
LOGO_OSCURO = Path("logo_traiguen_oscuro.png")  # blanco, para fondo carbón
LOGO_ICONO = Path("logo_icono.png")


def _logo_segun_tema() -> Path:
    """
    El logo azul se pierde sobre el gris carbón y el blanco desaparece sobre
    fondo claro, así que se elige según el modo que tenga activo la persona.
    Si no se puede saber el modo, se usa el azul, que es el original.
    """
    modo = "light"
    try:
        tema = st.context.theme
        # según la versión, viene como diccionario o como objeto
        modo = (tema.get("type") if hasattr(tema, "get") else getattr(tema, "type", None)) \
            or "light"
    except Exception:
        pass
    if modo == "dark" and LOGO_OSCURO.exists():
        return LOGO_OSCURO
    return LOGO_CLARO


def aplicar_apariencia(page_title: str):
    """
    Configuración de página + logo + estilo, común a la web y a la app de
    escritorio: layout ancho, ícono/título de pestaña, el logo según tema
    claro/oscuro, y el detalle de CSS del botón de anular pedido vacío (lo
    único que el tema de Streamlit no puede expresar por sí solo).
    """
    st.set_page_config(
        page_title=page_title,
        page_icon=str(LOGO_ICONO) if LOGO_ICONO.exists() else "📦",
        layout="wide",
    )

    logo = _logo_segun_tema()
    if logo.exists():
        try:
            st.logo(str(logo), size="large")
        except Exception:
            # versiones antiguas de Streamlit no tienen st.logo
            st.sidebar.image(str(logo), width=180)

    # Los colores del modo claro y oscuro se definen en .streamlit/config.toml,
    # que es el mecanismo propio de Streamlit. Acá solo queda el estilo del
    # botón de anular cuando un pedido quedó sin insumos: es un detalle que el
    # tema no puede expresar. Se evita a propósito tocar fondos y textos por
    # CSS, porque eso pisaba los estilos internos y dejaba el modo claro con
    # partes oscuras.
    st.markdown(
        """
        <style>
          @keyframes latido {
              0%   { box-shadow: 0 0 0 0 rgba(200,30,30,0.7); }
              70%  { box-shadow: 0 0 0 12px rgba(200,30,30,0); }
              100% { box-shadow: 0 0 0 0 rgba(200,30,30,0); }
          }
          .pedido-vacio button {
              background-color: #C81E1E !important;
              border-color: #C81E1E !important;
              color: #FFFFFF !important;
              animation: latido 1.4s infinite;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inicializar_estado_sesion():
    """Crea las claves de session_state que usa toda la interfaz, si todavia
    no existen. Debe llamarse una vez al principio de cada app."""
    if "carrito" not in st.session_state:
        st.session_state.carrito = []
    if "carrito_duenio" not in st.session_state:
        # A quién pertenece la lista que está en pantalla. Sin esto, la lista
        # quedaba viva al cambiar de cuenta: si el encargado agregaba un producto
        # y después entraba un solicitante en el mismo navegador, ese producto
        # aparecía dentro del pedido del solicitante.
        st.session_state.carrito_duenio = None
    if "correo_registrado" not in st.session_state:
        st.session_state.correo_registrado = None  # correo de la persona ya identificada en esta sesión
    if "form_nonce" not in st.session_state:
        st.session_state.form_nonce = 0  # se incrementa para limpiar los campos de búsqueda/cantidad
    if "ultimo_agregado" not in st.session_state:
        st.session_state.ultimo_agregado = None
    if "folio_recien_creado" not in st.session_state:
        st.session_state.folio_recien_creado = None
    if "folio_recien_cerrado" not in st.session_state:
        st.session_state.folio_recien_cerrado = None
    if "proceso_nonce" not in st.session_state:
        st.session_state.proceso_nonce = 0   # sirve para salir del detalle tras guardar
    if "aviso_proceso" not in st.session_state:
        st.session_state.aviso_proceso = None
    if "pedido_vacio" not in st.session_state:
        st.session_state.pedido_vacio = None
    if "folio_preparando" not in st.session_state:
        st.session_state.folio_preparando = None
    if "identidad_cache" not in st.session_state:
        st.session_state.identidad_cache = None
    if "alerta_sync_vista" not in st.session_state:
        st.session_state.alerta_sync_vista = False


def cargar_identidad_sesion(db_path):
    """
    Resuelve quien esta identificado en esta sesion (o None) y si es la
    cuenta de encargado. La cuenta de encargado se crea sola la primera vez.
    Devuelve (identidad_sesion, es_encargado).
    """
    _ok_encargado, _aviso_encargado = core.asegurar_encargado_por_defecto(db_path)
    if not _ok_encargado:
        st.error(_aviso_encargado)

    identidad_sesion = None
    if st.session_state.correo_registrado:
        persona = core.obtener_persona(st.session_state.correo_registrado)
        if persona:
            identidad_sesion = {"correo": st.session_state.correo_registrado, **persona}
            st.session_state.identidad_cache = identidad_sesion
        elif st.session_state.get("identidad_cache"):
            # La cuenta no se encontró en la base, pero la sesión sigue abierta en
            # este navegador. En el hosting gratuito la base se borra al reiniciar
            # el servidor, y sin esto la persona quedaba expulsada en medio de un
            # pedido. Se conserva la sesión con los datos ya conocidos.
            identidad_sesion = st.session_state.identidad_cache
        else:
            st.session_state.correo_registrado = None

    es_encargado = bool(identidad_sesion) and identidad_sesion.get("rol") == "encargado"

    return identidad_sesion, es_encargado


def cerrar_sesion():
    """Limpia todo el estado para que nada quede colgando entre personas."""
    st.session_state.correo_registrado = None
    st.session_state.carrito = []
    st.session_state.carrito_duenio = None
    st.session_state.folio_recien_creado = None
    st.session_state.folio_recien_cerrado = None
    st.session_state.ultimo_agregado = None


def mostrar_barra_sesion(identidad_sesion, es_encargado):
    """Caption de quien esta identificado + boton de cerrar sesion, arriba
    del titulo."""
    if identidad_sesion:
        _, col_sesion = st.columns([4, 1])
        with col_sesion:
            rol_texto = "Encargado de bodega" if es_encargado else "Solicitante"
            st.caption(f"{identidad_sesion['nombre']}  \n{rol_texto}")
            if st.button("Cerrar sesión", width='stretch'):
                cerrar_sesion()
                st.rerun()
        st.divider()


def mostrar_sidebar_cuenta(identidad_sesion):
    """Panel 'Mi cuenta' en la barra lateral (correo + cambiar contraseña)."""
    if identidad_sesion:
        with st.sidebar:
            st.subheader("Mi cuenta")
            st.caption(identidad_sesion["correo"])
            with st.expander("Cambiar contraseña"):
                actual = st.text_input("Contraseña actual", type="password", key="pass_actual")
                nueva1 = st.text_input("Nueva contraseña", type="password", key="pass_nueva1")
                nueva2 = st.text_input("Repetir nueva contraseña", type="password", key="pass_nueva2")
                if st.button("Actualizar contraseña"):
                    ok_pass, msg_pass = core.cambiar_password(
                        identidad_sesion["correo"], actual, nueva1, nueva2)
                    (st.success if ok_pass else st.error)(msg_pass)


# =====================================================================
#  VISTA SOLICITANTE (comun a ambos roles: el encargado tambien puede
#  generar solicitudes en nombre de alguien que llama por telefono, etc.)
# =====================================================================

def color_coincidencia(score):
    """
    Color según qué tan segura es la coincidencia:
      100%      -> se marca con estrella (es el producto exacto)
      60 a 99%  -> verde    (coincidencia buena)
      45 a 59%  -> amarillo (dudosa, conviene revisar)
      menos 45% -> rojo     (muy probablemente no es lo que busca)
    """
    if score >= 60:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def etiqueta_candidato(nombre, score, codigo=None):
    """Opción del buscador: estrella si es exacta, porcentaje coloreado si no."""
    sufijo = f"  ·  {codigo}" if codigo else ""
    if score >= 100:
        return f"⭐ **{nombre}**{sufijo}"
    color = color_coincidencia(score)
    return f":{color}[**{score:.0f}%**]  ·  {nombre}{sufijo}"


MENSAJE_SIN_RESULTADO = (
    "**NO EXISTE UN PRODUCTO REGISTRADO CON ESE NOMBRE.** "
    "Se recomienda consultar directamente al encargado por posibles discordancias "
    "en el inventario."
)
MENSAJE_AFINAR_BUSQUEDA = (
    "Si su producto no se encuentra en el motor de búsqueda, intente detallar más el "
    "producto agregando la marca, color o dimensiones."
)
MENSAJE_DERIVAR_ENCARGADO = (
    "Si el producto existe pero no aparece con ese nombre, diríjase al encargado de bodega "
    "para verificarlo manualmente. Él puede registrar esa forma de nombrarlo para que la "
    "próxima vez sí aparezca en el buscador."
)


def boton_descargar_archivo(ruta, etiqueta, nombre_archivo=None,
                             mime="application/octet-stream", key=None):
    """
    Botón de descarga de un archivo ya generado en disco. En la web (navegador
    real) es un st.download_button normal. En la app de escritorio (ventana
    nativa sin navegador, sin barra de descargas) un download_button no tiene
    dónde aterrizar y queda en silencio ("no pasa nada"), así que en su lugar
    se abre el archivo con el programa que Windows tenga asociado.
    """
    ruta = Path(ruta)
    if MODO_ESCRITORIO:
        if st.button(etiqueta, width='stretch', type="primary", key=key):
            try:
                os.startfile(str(ruta))  # noqa: S606 — abre con el programa asociado de Windows
            except OSError as e:
                st.error(f"No se pudo abrir el archivo automáticamente ({e}).")
        st.caption(f"Se abre con el programa asociado en Windows. Archivo: {ruta}")
        return

    with open(ruta, "rb") as f:
        datos = f.read()
    st.download_button(
        etiqueta, data=datos, file_name=nombre_archivo or ruta.name, mime=mime,
        width='stretch', type="primary", key=key,
    )


def boton_imprimir(folio, sufijo_key="", solo_comprobante=False, editable=True):
    """
    Genera el formulario que corresponde según quién lo pide:
      - Solicitante -> SOLICITUD DE MATERIALES (la lleva a firmar).
      - Encargado   -> COMPROBANTE MOVIMIENTOS EN BODEGA, y solo al cerrar el
        proceso; a esa altura la solicitud firmada ya está en sus manos.

    En el comprobante, el encargado puede editar el texto de INFORMACIÓN
    ADICIONAL antes de descargar: viene redactado por defecto y él completa
    o corrige lo que falte, en vez de imprimir una línea en blanco.
    """
    cabecera, items = core.datos_para_impresion(folio)
    if cabecera is None:
        st.error("No se encontró la solicitud para imprimir.")
        return

    correlativo = cabecera.get("correlativo")

    if solo_comprobante and editable:
        st.markdown("**Datos editables del comprobante**")
        st.caption("Revise o corrija antes de descargar; sale impreso tal cual.")

        # El área que escribe el solicitante suele ser el nombre corto
        # ("FINANZAS") y no el nombre formal de la dirección de origen
        # ("DIRECCIÓN DE ADMINISTRACIÓN Y FINANZAS"), por eso es editable.
        depto = st.text_input(
            "Depto. origen",
            value=cabecera.get("depto_origen") or cabecera.get("area_departamento") or "",
            key=f"depto_{folio}_{sufijo_key}",
        )
        # Memo, tipo de movimiento y destino: vienen prescritos con el valor
        # de siempre, pero quedan editables por si el encargado necesita
        # cambiarlos para un movimiento particular.
        c_memo, c_tipo, c_destino = st.columns(3)
        memo = c_memo.text_input(
            "Memo",
            value=cabecera.get("memo") or formato_impresion.MEMO_POR_DEFECTO,
            key=f"memo_{folio}_{sufijo_key}",
        )
        tipo_mov = c_tipo.text_input(
            "Tipo movimiento",
            value=cabecera.get("tipo_movimiento") or formato_impresion.TIPO_MOVIMIENTO_POR_DEFECTO,
            key=f"tipomov_{folio}_{sufijo_key}",
        )
        destino = c_destino.text_input(
            "Destino",
            value=cabecera.get("destino") or formato_impresion.DESTINO_POR_DEFECTO,
            key=f"destino_{folio}_{sufijo_key}",
        )
        texto = st.text_area(
            "Información adicional",
            value=cabecera.get("info_adicional") or core.texto_info_adicional(cabecera),
            key=f"info_{folio}_{sufijo_key}", height=90,
        )
        if st.button("Guardar cambios", key=f"guardar_info_{folio}_{sufijo_key}"):
            core.guardar_depto_origen(folio, depto)
            core.guardar_info_adicional(folio, texto)
            core.guardar_memo(folio, memo)
            core.guardar_tipo_movimiento(folio, tipo_mov)
            core.guardar_destino(folio, destino)
            st.success("Cambios guardados.")
            st.rerun()

        cabecera["depto_origen"] = depto
        cabecera["info_adicional"] = texto
        cabecera["memo"] = memo
        cabecera["tipo_movimiento"] = tipo_mov
        cabecera["destino"] = destino
        ruta = CARPETA_PDF / f"comprobante_{correlativo}.pdf"
        formato_impresion.generar_comprobante_pdf(ruta, cabecera, items)
        etiqueta = f"Imprimir comprobante n° {correlativo}"
        nombre_archivo = f"comprobante_{correlativo}.pdf"
    elif solo_comprobante:
        # reimpresión desde el historial: se emite tal como quedó guardado,
        # sin volver a mostrar los campos de edición
        ruta = CARPETA_PDF / f"comprobante_{correlativo}.pdf"
        formato_impresion.generar_comprobante_pdf(ruta, cabecera, items)
        etiqueta = f"Imprimir comprobante n° {correlativo}"
        nombre_archivo = f"comprobante_{correlativo}.pdf"
    else:
        ruta = CARPETA_PDF / f"solicitud_{correlativo}.pdf"
        formato_impresion.generar_solicitud_pdf(ruta, cabecera, items)
        etiqueta = f"Imprimir solicitud n° {correlativo}"
        nombre_archivo = f"solicitud_{correlativo}.pdf"

    if MODO_ESCRITORIO:
        # La app corre en una ventana nativa (pywebview), no en un navegador
        # real: ahí no hay barra de descargas ni pestañas nuevas, así que
        # tanto el download_button como el truco de blob+window.open de abajo
        # quedan sin efecto visible ("no pasa nada"). En su lugar se abre el
        # PDF ya generado con el visor que Windows tenga asociado — desde ahí
        # el propio visor ofrece Guardar como e Imprimir de forma nativa.
        if st.button(etiqueta, width='stretch', type="primary",
                     key=f"abrir_{folio}_{sufijo_key}"):
            try:
                os.startfile(str(ruta))  # noqa: S606 — abre con el visor asociado de Windows
            except OSError as e:
                st.error(f"No se pudo abrir el PDF automáticamente ({e}).")
        st.caption(f"Se abre en su visor de PDF — desde ahí puede Guardar como o Imprimir. "
                   f"Archivo: {ruta}")
        return

    with open(ruta, "rb") as f:
        datos_pdf = f.read()

    # La descarga sigue siendo la opción principal (barra ancha). Al lado va
    # la impresión directa, que abre el documento en una pestaña con el visor
    # del navegador: desde ahí se manda a cualquier impresora conectada al
    # equipo, sin guardar el archivo.
    col_descarga, col_imprimir = st.columns([4, 1])
    with col_descarga:
        st.download_button(
            etiqueta, data=datos_pdf, file_name=nombre_archivo, mime="application/pdf",
            width='stretch', type="primary", key=f"print_{folio}_{sufijo_key}",
        )
    with col_imprimir:
      # Se envuelve en try/except: components.html está marcado como obsoleto
      # y, si algún día se retira, la app debe seguir funcionando con el botón
      # de descarga en vez de caerse.
      try:
        b64 = base64.b64encode(datos_pdf).decode()
        components.html(
            f"""
            <button id="btn" style="width:100%;height:38px;cursor:pointer;
                border:1px solid #4899CF;border-radius:8px;background:#FFFFFF;
                color:#1B4F72;font-weight:600;font-size:13px;">
                🖨️ Imprimir
            </button>
            <script>
              const datos = atob("{b64}");
              const bytes = new Uint8Array(datos.length);
              for (let i = 0; i < datos.length; i++) bytes[i] = datos.charCodeAt(i);
              const url = URL.createObjectURL(
                  new Blob([bytes], {{type: "application/pdf"}}));
              document.getElementById("btn").onclick = () => window.open(url, "_blank");
            </script>
            """,
            height=46,
        )
        st.caption("Abre el PDF para imprimir")
      except Exception:
        st.caption("Use el botón de descarga y abra el archivo para imprimir.")


def panel_acceso():
    """
    Puerta de entrada para solicitantes: pestaña de ingreso (correo +
    contraseña) y pestaña de registro por única vez. El registro exige que
    el correo esté en la nómina autorizada por el encargado; la contraseña
    se pide dos veces para asegurarse de que quedó bien escrita.
    """
    st.subheader("Acceso de solicitantes")
    tab_login, tab_registro = st.tabs(["Ingresar", "Registrarme por primera vez"])

    with tab_login:
        correo = st.text_input("Correo institucional", key="login_correo",
                               placeholder="nombre.apellido@dominio.cl")
        password = st.text_input("Contraseña", type="password", key="login_pass")
        if st.button("Ingresar", type="primary"):
            ok, mensaje = core.verificar_login(correo, password)
            if ok:
                st.session_state.correo_registrado = correo.strip().lower()
                st.rerun()
            else:
                st.error(mensaje)

    with tab_registro:
        st.caption(
            "El registro se hace una sola vez. Después entra siempre con su correo "
            "y la contraseña que cree aquí."
        )
        correo_r = st.text_input("Correo institucional", key="reg_correo",
                                 placeholder="nombre.apellido@dominio.cl")

        if not correo_r:
            return
        correo_r = correo_r.strip().lower()

        if core.obtener_persona(correo_r):
            st.info("Este correo ya está registrado. Use la pestaña 'Ingresar'.")
            return

        if not core.formato_correo_valido(correo_r):
            st.error(f'"{correo_r}" no tiene formato de correo válido.')
            return

        # El dominio correcto no prueba que el correo exista ni que sea suyo.
        # El control real es la lista de correos que el encargado autorizó.
        if not core.correo_autorizado(correo_r):
            st.error(
                f'El correo "{correo_r}" no está en la nómina de correos autorizados '
                "para hacer solicitudes."
            )
            st.info(
                "Si usted trabaja en la municipalidad y necesita acceso, solicite al "
                "encargado de bodega que agregue su correo a la nómina autorizada."
            )
            return

        st.success("Correo autorizado. Complete sus datos:")
        nombre = st.text_input("Su nombre completo", key="reg_nombre")
        area = st.text_input("Área / Departamento", key="reg_area", placeholder="ej. Finanzas")
        nombre_supervisor = st.text_input(
            "Nombre de su supervisor/jefatura", key="reg_sup",
            placeholder="ej. Cristian San Miguel",
        )
        password1 = st.text_input("Cree una contraseña", type="password", key="reg_pass1")
        password2 = st.text_input("Repita la contraseña", type="password", key="reg_pass2")

        if st.button("Completar registro", type="primary"):
            errores = []
            if not nombre.strip():
                errores.append("nombre")
            if not area.strip():
                errores.append("área/departamento")
            if not nombre_supervisor.strip():
                errores.append("nombre del supervisor")
            if errores:
                st.error("Faltan datos: " + ", ".join(errores))
                return
            ok, mensaje = core.validar_password(password1, password2)
            if not ok:
                st.error(mensaje)
                return
            core.registrar_persona(correo_r, nombre, area, nombre_supervisor, password1)
            st.session_state.correo_registrado = correo_r
            st.success("Registro completado.")
            st.rerun()


def asegurar_carrito_de(duenio):
    """
    Cada cuenta tiene su propia lista de productos. Si la lista en pantalla
    pertenece a otra cuenta (porque el encargado la armó antes, o porque
    entró otra persona en el mismo navegador), se descarta y se parte de
    cero. Sin esto, un producto agregado por el encargado terminaba metido
    dentro del pedido del siguiente usuario que iniciara sesión.
    """
    if st.session_state.carrito_duenio != duenio:
        st.session_state.carrito = []
        st.session_state.carrito_duenio = duenio
        st.session_state.folio_recien_creado = None
        st.session_state.ultimo_agregado = None


def panel_nueva_solicitud(es_encargado: bool, identidad: dict = None):
    """
    identidad: si viene (flujo solicitante ya registrado), el nombre sale del
    registro. Si es None (flujo encargado), se piden los datos a mano.

    La lista de productos queda aislada por cuenta (ver asegurar_carrito_de).
    """
    # Identificador de la cuenta dueña de esta lista: el correo del
    # solicitante, o "ENCARGADO" cuando lo arma el encargado.
    duenio = identidad["correo"] if identidad else "__ENCARGADO__"
    asegurar_carrito_de(duenio)

    st.subheader("1. Buscar producto")

    # Las claves de los widgets llevan un 'nonce' que se incrementa cada vez
    # que se agrega un producto. Al cambiar la clave, Streamlit los crea de
    # nuevo vacíos — así se limpia solo el texto buscado y la cantidad, sin
    # que la persona tenga que borrarlos a mano, y sin tocar el carrito.
    n = st.session_state.form_nonce
    busqueda = st.text_input("Busque el producto que desea", key=f"busqueda_input_{n}")

    if busqueda:
        # umbral bajo a propósito: así también se ven las coincidencias malas
        # pintadas en rojo, en vez de esconderlas y dejar la pantalla vacía.
        candidatos = core.buscar_producto(busqueda, umbral=35, limite=7)
        if candidatos:
            opciones = [
                etiqueta_candidato(nombre, score, codigo if es_encargado else None)
                for codigo, nombre, score in candidatos
            ]
            st.caption(
                "⭐ es coincidencia exacta, pero igual se muestran las demás opciones "
                "parecidas. El porcentaje indica qué tan segura es cada una: "
                ":green[**verde**] buena · :yellow[**amarillo**] dudosa · "
                ":red[**rojo**] poco confiable."
            )
            multiple = st.checkbox(
                "Selección múltiple", key=f"multi_{n}",
                help="Permite marcar varios productos de esta misma búsqueda. "
                     "Las cantidades se ajustan después, en la lista de la solicitud.",
            )

            if multiple:
                # Casillas individuales y no un menú desplegable: los menús de
                # Streamlit no muestran colores en sus opciones, y ahí se perdía
                # la señal de confianza de cada coincidencia.
                marcados = []
                for indice, etiqueta in enumerate(opciones):
                    if st.checkbox(etiqueta, key=f"chk_{n}_{indice}"):
                        marcados.append(indice)

                if marcados and st.button(
                        f"Agregar {len(marcados)} producto(s) a la solicitud",
                        type="primary"):
                    agregados = []
                    for indice in marcados:
                        codigo, nombre, score = candidatos[indice]
                        if score < 100 and es_encargado:
                            core.registrar_alias_nuevo(busqueda, codigo)
                        st.session_state.carrito.append((codigo, nombre, 1))
                        agregados.append(nombre)
                    st.session_state.ultimo_agregado = (
                        f"{len(agregados)} producto(s) — ajuste las cantidades abajo")
                    st.session_state.form_nonce += 1
                    st.rerun()
            else:
                seleccion = st.radio("Coincidencias encontradas:", opciones,
                                     key=f"radio_sel_{n}")
                cantidad = st.number_input("Cantidad", min_value=1, step=1,
                                           key=f"cant_input_{n}")

                if st.button("Agregar a la solicitud", type="primary"):
                    idx = opciones.index(seleccion)
                    codigo, nombre, score = candidatos[idx]
                    if score < 100 and es_encargado:
                        core.registrar_alias_nuevo(busqueda, codigo)
                    st.session_state.carrito.append((codigo, nombre, cantidad))
                    st.session_state.ultimo_agregado = f"{nombre} x{cantidad}"
                    st.session_state.form_nonce += 1
                    st.rerun()

            st.info(MENSAJE_AFINAR_BUSQUEDA)
        else:
            core.registrar_alias_pendiente(busqueda)
            st.error(MENSAJE_SIN_RESULTADO)
            st.info(MENSAJE_DERIVAR_ENCARGADO)

    if st.session_state.get("ultimo_agregado"):
        st.success(f"Agregado: {st.session_state.ultimo_agregado}")
        st.session_state.ultimo_agregado = None

    if st.session_state.carrito:
        st.subheader("2. Productos en esta solicitud")

        # Cada producto en su propia fila con una ✕ a la derecha para sacarlo
        # individualmente. Antes solo existía "vaciar lista", que obligaba a
        # rehacer todo el pedido por equivocarse en un solo ítem.
        for indice, (codigo, nombre, cantidad) in enumerate(list(st.session_state.carrito)):
            col_texto, col_cant, col_x = st.columns([8, 2, 1])
            etiqueta = f"**{nombre}**" + (f"  ·  {codigo}" if es_encargado else "")
            col_texto.markdown(etiqueta)
            # la cantidad se puede corregir acá mismo, sin sacar y volver a
            # agregar el producto
            nueva_cantidad = col_cant.number_input(
                f"cantidad {codigo}", min_value=1, step=1, value=int(cantidad),
                key=f"cant_carrito_{indice}_{codigo}", label_visibility="collapsed",
            )
            if nueva_cantidad != cantidad:
                st.session_state.carrito[indice] = (codigo, nombre, nueva_cantidad)
                st.rerun()
            if col_x.button("✕", key=f"quitar_{indice}_{codigo}",
                            help=f"Quitar {nombre} de la solicitud"):
                st.session_state.carrito.pop(indice)
                st.rerun()
            st.divider()

        st.subheader("3. Datos de la solicitud")
        if identidad:
            # El nombre viene del registro: la persona ya se identificó al
            # entrar, no tiene por qué volver a escribirlo (ni podría cambiarlo).
            solicitante = identidad["nombre"]
            correo_solicitante = identidad["correo"]
            correo_supervisor = identidad.get("correo_supervisor") or ""
            st.markdown(f"**Solicitante:** {solicitante}")

            # Área, oficina y supervisor quedan editables: una misma persona
            # podría estar pidiendo para otro departamento, otra oficina o con
            # otra jefatura. La oficina no se pide en el registro, solo acá.
            c1, c2 = st.columns(2)
            area = c1.text_input("Área / Departamento",
                                 value=identidad.get("area_departamento") or "")
            oficina = c2.text_input("Oficina", placeholder="ej. archivo e inventario")
            supervisor = st.text_input("Supervisor / jefatura que firma",
                                       value=identidad.get("nombre_supervisor") or "")
        else:
            solicitante = st.text_input("Solicitante")
            c1, c2 = st.columns(2)
            area = c1.text_input("Área / Departamento")
            oficina = c2.text_input("Oficina", placeholder="ej. archivo e inventario")
            supervisor = st.text_input("Supervisor / jefe (firma pendiente en papel)")
            correo_solicitante = None
            correo_supervisor = None

        if st.button("Registrar solicitud (queda 'pendiente de firma')"):
            items = [(c, cant) for c, _, cant in st.session_state.carrito]
            try:
                folio = core.crear_solicitud(
                    solicitante, supervisor, area, items,
                    correo_solicitante=correo_solicitante, correo_supervisor=correo_supervisor,
                    oficina=oficina,
                )
            except ValueError as e:
                st.error(str(e))
                st.warning("La solicitud NO se guardó — complete todos los datos obligatorios e intente de nuevo.")
            else:
                st.session_state.folio_recien_creado = folio
                st.session_state.carrito = []
                st.rerun()

    # Tras registrar, se muestra el folio y el botón de impresión grande.
    if st.session_state.get("folio_recien_creado"):
        folio = st.session_state.folio_recien_creado
        cabecera, _ = core.datos_para_impresion(folio)
        st.success(
            f"Solicitud registrada — **N° {cabecera['correlativo']}**  \n"
            f"Imprima el formulario, hágalo firmar y timbrar, y llévelo a bodega."
        )
        boton_imprimir(folio, sufijo_key="nueva")
        df = core.resumen_solicitud(folio)
        for _, fila in df.iterrows():
            if fila["mensaje_sistema"]:
                st.warning(f"{fila['producto']}: {fila['mensaje_sistema']}")
        if st.button("Hacer otra solicitud"):
            st.session_state.folio_recien_creado = None
            st.rerun()


def panel_mis_solicitudes(identidad: dict):
    st.subheader("Mis solicitudes")
    df = core.solicitudes_de_correo(identidad["correo"])
    if df.empty:
        st.info("No hay solicitudes registradas con tu correo todavía.")
    else:
        etiquetas_estado = {
            "pendiente_firma": "Pendiente de que traigas el papel firmado",
            "preliminar_aceptada": "Papel recibido, en revisión en bodega",
            "editada": "En bodega, cantidades ajustadas",
            "cerrada": "Entregada",
            "anulada": "Anulada",
        }
        df["estado"] = df["estado"].map(etiquetas_estado).fillna(df["estado"])
        st.dataframe(df, width='stretch', hide_index=True)
