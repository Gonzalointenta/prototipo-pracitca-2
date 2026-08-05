# -*- coding: utf-8 -*-
"""
app_encargado.py — versión de escritorio para el encargado de bodega.

Con Supabase configurado (SUPABASE_DB_URL), esta app y la web (app.py) leen
y escriben la misma base compartida — una solicitud creada en la web
aparece de inmediato acá. Sin esa variable, cae de vuelta a una base SQLite
local en la carpeta de datos de la app (comportamiento original, antes de
tener una base compartida en la nube).

Cada sesión guarda además una FOTO de respaldo en el propio equipo (ver
core.respaldar_base_local) — no es una réplica en vivo ni algo de donde se
lee: solo un resguardo "por si acaso" ante un corte de internet o un
problema con el servicio.

Reutiliza el mismo login y los mismos paneles que la web (ver
interfaz_comun.py / interfaz_encargado.py): un arreglo o mejora hecho en
cualquiera de las dos interfaces queda disponible en ambas, sin mantener dos
copias del mismo código.

Ejecutar con:  streamlit run app_encargado.py
(o el acceso directo que abre el .exe empaquetado — ver DESPLIEGUE.md)
"""

import os
from pathlib import Path

import streamlit as st

import core
from catalogo_real import PRODUCTOS
import interfaz_comun
from interfaz_comun import (
    aplicar_apariencia,
    cargar_identidad_sesion,
    cerrar_sesion,
    inicializar_estado_sesion,
    panel_acceso,
    panel_mi_cuenta,
    panel_nueva_solicitud,
)
from interfaz_encargado import (
    panel_correos_autorizados,
    panel_crear_alias,
    panel_estadisticas,
    panel_gestion_accesos,
    panel_historial,
    panel_importar_saldos,
    panel_inventario_critico,
    panel_inventario_general,
    panel_pedidos_completados,
    panel_solicitudes_activas,
    panel_sync_smc,
)

aplicar_apariencia("Bodega Municipal de Traiguén — Encargado")

# --------------------------------------------------------- datos locales
# Carpeta de datos de la app en el PC del encargado (no al lado del .exe):
# así los datos sobreviven aunque el ejecutable se mueva, se reemplace por
# una versión nueva, o se abra desde un acceso directo distinto.
CARPETA_DATOS = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "BodegaTraiguenEncargado"
CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

DB_PATH = str(CARPETA_DATOS / "bodega_local.db")
core.DB_PATH = DB_PATH

# Con Supabase configurado, este mismo archivo deja de ser la base "de
# verdad" (get_connection() apunta a Supabase) y pasa a ser el destino del
# respaldo periódico — ver el bloque más abajo, después del login.
RUTA_RESPALDO = DB_PATH

# Los comprobantes/solicitudes en PDF también quedan en la carpeta de datos,
# no en el directorio desde donde se ejecute la app (que al empaquetar como
# .exe no siempre es un lugar predecible ni escribible).
interfaz_comun.CARPETA_PDF = CARPETA_DATOS / "formularios"
interfaz_comun.CARPETA_PDF.mkdir(exist_ok=True)

# El Excel del historial va al Escritorio, con un nombre claro, para que quede
# a la vista y a mano. Es UN solo archivo que se va actualizando en su lugar:
# antes quedaba en la ruta relativa por defecto ("exportes/historial_bodega.
# xlsx"), que en el .exe se resuelve contra un directorio temporal distinto en
# cada arranque, así que "actualizar" el Excel dejaba en realidad un archivo
# suelto nuevo cada vez. Con una ruta fija, exportar_historial_excel()
# sobrescribe siempre este mismo archivo y el botón abre siempre ese.
def _carpeta_escritorio() -> Path:
    """
    Ruta real del Escritorio del usuario. Se lee del registro de Windows y no
    se asume %USERPROFILE%\\Desktop porque con OneDrive el Escritorio suele
    estar redirigido a una carpeta dentro de OneDrive; el registro apunta al
    lugar correcto en ambos casos. Si algo falla, cae al Escritorio clásico.
    """
    try:
        import winreg
        clave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave) as k:
            valor, _ = winreg.QueryValueEx(k, "Desktop")
        carpeta = Path(os.path.expandvars(valor))
        if carpeta.is_dir():
            return carpeta
    except Exception:
        pass
    return Path.home() / "Desktop"


core.RUTA_EXCEL_HISTORIAL = str(_carpeta_escritorio() / "Bodega Municipal - Historial.xlsx")

# La app corre en una ventana nativa (ver escritorio_encargado.py), no en un
# navegador real: los botones de descarga/impresión de interfaz_comun.py e
# interfaz_encargado.py abren el PDF con el visor asociado de Windows en vez
# de intentar un download_button o un window.open, que ahí no tienen efecto.
interfaz_comun.MODO_ESCRITORIO = True

# Streamlit vuelve a correr TODO el script en cada click, no solo la primera
# vez: sin esta guarda, init_db() (11 CREATE TABLE + 19 ALTER TABLE de
# migración) se repetía en cada interacción aunque la base ya estuviera al
# día, sumando ~30 round-trips por click contra la base remota.
if not st.session_state.get("db_inicializada"):
    core.init_db(DB_PATH)  # idempotente: crea tablas si faltan, migra columnas si la base es antigua
    if not core.catalogo_cargado(DB_PATH):
        # ver la nota en app.py: actualizar_valores_catalogo solo se corre junto
        # con la carga inicial, no en cada arranque (contra la base remota es caro).
        core.cargar_catalogo(PRODUCTOS, DB_PATH)
        core.actualizar_valores_catalogo(DB_PATH)
    st.session_state.db_inicializada = True

inicializar_estado_sesion()
identidad_sesion, es_encargado = cargar_identidad_sesion(DB_PATH)

st.title("Bodega Municipal — Encargado")
if core.SUPABASE_DB_URL:
    st.caption("Datos guardados en la base compartida (Supabase) — los mismos que ve la web.")
else:
    st.caption(f"Datos guardados en este equipo: {DB_PATH}")

if not identidad_sesion:
    # Sin sesión iniciada no se muestra nada más: se pide el mismo login que
    # en la web (misma cuenta de encargado, misma contraseña).
    panel_acceso()
    st.stop()

if not es_encargado:
    st.error(
        "Esta aplicación es solo para la cuenta de encargado de bodega. "
        f"La cuenta \"{identidad_sesion['correo']}\" no tiene ese rol."
    )
    if st.button("Cerrar sesión"):
        cerrar_sesion()
        st.rerun()
    st.stop()

# La identidad y el botón de cerrar sesión viven ahora en la barra lateral
# (ver más abajo, junto al selector de modo claro/oscuro), no en el encabezado.
st.divider()

# Respaldo local: una vez por sesión, no en cada rerun (Streamlit vuelve a
# correr todo el script con cada clic). Solo tiene sentido si hay una base
# remota de la cual respaldar — contra SQLite local ya es el mismo archivo.
if core.SUPABASE_DB_URL and not st.session_state.get("respaldo_local_hecho"):
    try:
        core.respaldar_base_local(RUTA_RESPALDO)
        st.session_state.respaldo_local_hecho = True
    except Exception as e:
        # El respaldo es un "por si acaso", no algo crítico: si falla (ej.
        # sin internet en este preciso momento) no debe frenar el resto de
        # la app, que sigue funcionando contra Supabase igual.
        st.session_state.respaldo_local_hecho = True
        st.caption(f"⚠️ No se pudo generar el respaldo local esta vez: {e}")

# El acceso a la cuenta (datos, contraseña, cerrar sesión) ahora es una sección
# ("Mi Cuenta") a la que se llega desde el bloque de cuenta al pie del menú
# lateral. El menú se arma más abajo (lista de secciones + cuenta al fondo).

if core.actualizacion_semanal_pendiente():
    if not st.session_state.alerta_sync_vista:
        c_alerta, c_cerrar = st.columns([6, 1])
        with c_alerta:
            st.error(
                "⚠️ **Falta importar los saldos de SMC esta semana.** Corresponde "
                "escanear el listado y subirlo al empezar la jornada del lunes — lo que "
                "muestra el sistema puede no coincidir con el inventario real hasta "
                "que se actualice en la pestaña *Actualizar saldos*."
            )
        with c_cerrar:
            if st.button("Entendido"):
                st.session_state.alerta_sync_vista = True
                st.rerun()

# Nombre y apellido de quien procesa: va impreso en el comprobante como
# responsable del movimiento.
if core.nombre_encargado() != identidad_sesion["nombre"]:
    core.guardar_config("nombre_encargado", identidad_sesion["nombre"])

# La pestaña "Gestionar accesos" (dar/quitar rol de encargado) la ven SOLO los
# administradores (creador y supervisor), no el encargado común.
es_admin = identidad_sesion.get("rol") == "admin"

etiquetas_tabs = [
    "Nueva solicitud", "Solicitudes activas", "Pedidos completados",
    "Inventario general", "Inventario crítico", "Actualizar saldos",
    "Historial", "Estadísticas", "Crear alias", "Correos autorizados",
    "Sincronización SMC",
]
if es_admin:
    etiquetas_tabs.append("Gestionar accesos")
# "Mi Cuenta" NO va en la lista scrolleable: se llega desde el bloque de cuenta
# al pie del menú (ver más abajo). Igual necesita su entrada en _PANELES.

# Navegación por la barra lateral: se ejecuta y renderiza SOLO la sección
# elegida. Antes esto era st.tabs, que corre el código de las 11-12 pestañas en
# CADA rerun (cada tecla/clic), disparando las consultas de todos los paneles a
# la vez contra Supabase (~85 ms cada una) y generando el lag. Con el menú
# lateral (lista de secciones) corre un único panel por interacción.
_PANELES = {
    "Nueva solicitud": lambda: panel_nueva_solicitud(es_encargado=True),
    "Solicitudes activas": panel_solicitudes_activas,
    "Pedidos completados": panel_pedidos_completados,
    "Inventario general": panel_inventario_general,
    "Inventario crítico": panel_inventario_critico,
    "Actualizar saldos": panel_importar_saldos,
    "Historial": panel_historial,
    "Estadísticas": panel_estadisticas,
    "Crear alias": panel_crear_alias,
    "Correos autorizados": panel_correos_autorizados,
    "Sincronización SMC": panel_sync_smc,
    "Gestionar accesos": panel_gestion_accesos,
    "Mi Cuenta": lambda: panel_mi_cuenta(identidad_sesion),
}

# --- Menú lateral estilo lista + cuenta al pie (como en apps tipo Claude) ---
# La lista de secciones scrollea sola (así entran más pantallas a futuro) y el
# bloque de cuenta queda fijo abajo, siempre visible. El CSS hace del bloque
# raíz del sidebar una columna que llena el alto; el contenedor de la lista
# (st-key-nav_scroll) toma el espacio libre y scrollea, y lo que va después
# (la cuenta) queda pegado al fondo. Sigue corriendo un solo panel por rerun.
st.markdown(
    """
    <style>
    /* el contenedor externo del sidebar NO scrollea: el único scroll es el de
       la lista de secciones (.st-key-nav_scroll). Así se elimina la barra de
       scroll redundante del sidebar, dejando solo la de "ir entre herramientas". */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{ overflow:hidden !important; }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"]{
        display:flex; flex-direction:column; height: calc(100vh - 90px); overflow:hidden;
    }
    [data-testid="stLayoutWrapper"]:has(> [data-testid="stVerticalBlock"].st-key-nav_scroll){
        flex:1 1 auto; min-height:0; display:flex;
    }
    .st-key-nav_scroll{
        flex:1 1 auto; min-height:0; overflow-y:auto; padding:0 .25rem 0 0 !important;
    }
    section[data-testid="stSidebar"] .stButton>button{
        justify-content:flex-start; text-align:left; font-weight:500;
    }
    .st-key-nav_scroll [data-testid="stElementContainer"]{ margin-bottom:-.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sección activa: se guarda a mano en session_state (antes lo manejaba el radio).
_secciones_validas = etiquetas_tabs + ["Mi Cuenta"]
if st.session_state.get("seccion_encargado") not in _secciones_validas:
    st.session_state.seccion_encargado = etiquetas_tabs[0]

with st.sidebar:
    with st.container(key="nav_scroll"):
        for _label in etiquetas_tabs:
            _activo = st.session_state.seccion_encargado == _label
            if st.button(_label, key=f"nav_{_label}", width="stretch",
                         type="primary" if _activo else "tertiary"):
                st.session_state.seccion_encargado = _label
                st.rerun()

    # Bloque de cuenta, pegado al fondo del menú.
    st.divider()
    st.caption(f"👤 **{identidad_sesion['nombre']}**")
    st.caption(identidad_sesion["correo"])
    if st.button("Mi Cuenta", key="btn_micuenta", width="stretch",
                 type="primary" if st.session_state.seccion_encargado == "Mi Cuenta" else "secondary"):
        st.session_state.seccion_encargado = "Mi Cuenta"
        st.rerun()
    st.caption("🎨 Modo claro/oscuro: menú ☰")

_PANELES[st.session_state.seccion_encargado]()
