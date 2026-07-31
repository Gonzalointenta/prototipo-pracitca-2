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
    mostrar_sidebar_cuenta,
    panel_acceso,
    panel_nueva_solicitud,
)
from interfaz_encargado import (
    panel_correos_autorizados,
    panel_crear_alias,
    panel_estadisticas,
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

_, col_sesion = st.columns([4, 1])
with col_sesion:
    st.caption(f"{identidad_sesion['nombre']}  \nEncargado de bodega")
    if st.button("Cerrar sesión", width='stretch'):
        cerrar_sesion()
        st.rerun()
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

mostrar_sidebar_cuenta(identidad_sesion)

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

tabs = st.tabs([
    "Nueva solicitud", "Solicitudes activas", "Pedidos completados",
    "Inventario general", "Inventario crítico", "Actualizar saldos",
    "Historial", "Estadísticas", "Crear alias", "Correos autorizados",
    "Sincronización SMC",
])
with tabs[0]:
    panel_nueva_solicitud(es_encargado=True)
with tabs[1]:
    panel_solicitudes_activas()
with tabs[2]:
    panel_pedidos_completados()
with tabs[3]:
    panel_inventario_general()
with tabs[4]:
    panel_inventario_critico()
with tabs[5]:
    panel_importar_saldos()
with tabs[6]:
    panel_historial()
with tabs[7]:
    panel_estadisticas()
with tabs[8]:
    panel_crear_alias()
with tabs[9]:
    panel_correos_autorizados()
with tabs[10]:
    panel_sync_smc()
