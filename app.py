# -*- coding: utf-8 -*-
"""
app.py — Bodega Municipal, vista SOLICITANTE (web pública).

La vista de Encargado ya no vive acá: corre exclusivamente en la app de
escritorio (ver app_encargado.py / escritorio_encargado.py), para que la web
pública no necesite los requerimientos ni las cargas de archivos que son
exclusivas de bodega (OCR de PDF escaneado, importación de Excel, etc.) — ver
requirements.txt/packages.txt, que quedaron más chicos por lo mismo.

Ambas apps comparten la misma base de datos (Supabase/Postgres, ver core.py
y supabase_pg.py): una solicitud creada acá aparece de inmediato en
"Solicitudes activas" de la app de escritorio, y la nómina de correos
autorizados que administra el encargado desde el .exe es la misma que usa
esta web para dejar entrar (o no) a un solicitante nuevo.

Los paneles en sí (login, "Nueva solicitud", "Mis solicitudes") viven en
interfaz_comun.py, compartido con la app de escritorio, así que un arreglo
hecho acá queda disponible en las dos sin mantener dos copias del código.
"""

import streamlit as st

import core
from catalogo_real import PRODUCTOS
from interfaz_comun import (
    aplicar_apariencia,
    cargar_identidad_sesion,
    cerrar_sesion,
    inicializar_estado_sesion,
    mostrar_barra_sesion,
    mostrar_sidebar_cuenta,
    panel_acceso,
    panel_mis_solicitudes,
    panel_nueva_solicitud,
)

aplicar_apariencia("Bodega Municipal de Traiguén")

DB_PATH = "bodega.db"  # solo se usa si no hay credenciales de Supabase configuradas
core.DB_PATH = DB_PATH

# Streamlit vuelve a correr TODO el script en cada click, no solo la primera
# vez: sin esta guarda, init_db() (11 CREATE TABLE + 19 ALTER TABLE de
# migración) se repetía en cada interacción aunque la base ya estuviera al
# día, sumando ~30 round-trips por click contra la base remota.
if not st.session_state.get("db_inicializada"):
    core.init_db(DB_PATH)  # idempotente: crea tablas si faltan, migra columnas si la base es antigua
    if not core.catalogo_cargado(DB_PATH):
        # actualizar_valores_catalogo solo hace falta junto con la carga inicial:
        # es un backfill para bases viejas de antes de que existiera valor_saldo.
        # Repetirlo en cada arranque era gratis contra SQLite local, pero contra
        # la base remota son ~290 UPDATE por red — varios minutos en cada carga de página.
        core.cargar_catalogo(PRODUCTOS, DB_PATH)
        core.actualizar_valores_catalogo(DB_PATH)
    st.session_state.db_inicializada = True


# El control de acceso es la nómina de correos que autoriza el encargado
# desde la app de escritorio (pestaña "Correos autorizados" ahí) — no el
# dominio: se aceptan direcciones de cualquier dominio siempre que estén
# autorizadas.

inicializar_estado_sesion()

# ------------------------------------------------- identidad de la sesión
identidad_sesion, es_encargado = cargar_identidad_sesion(DB_PATH)

mostrar_barra_sesion(identidad_sesion, es_encargado)

st.title("Bodega Municipal")

mostrar_sidebar_cuenta(identidad_sesion)

# =====================================================================
#  Esta web es solo para solicitantes — la vista de encargado corre en
#  la app de escritorio, no acá.
# =====================================================================

if es_encargado:
    st.error(
        "La cuenta de encargado no se usa desde la web. Para procesar solicitudes, "
        "revisar inventario o cualquier otra tarea de bodega, abra la aplicación de "
        "escritorio instalada en su equipo."
    )
    if st.button("Cerrar sesión"):
        cerrar_sesion()
        st.rerun()
elif identidad_sesion:
    tabs = st.tabs(["Nueva solicitud", "Mis solicitudes"])
    with tabs[0]:
        st.caption("Catálogo real de 290 productos, con búsqueda por alias.")
        panel_nueva_solicitud(es_encargado=False, identidad=identidad_sesion)
    with tabs[1]:
        panel_mis_solicitudes(identidad_sesion)
else:
    # Sin sesión iniciada no se muestra ninguna pestaña: así se evita que
    # cualquiera con el link pida a nombre de un tercero.
    panel_acceso()
