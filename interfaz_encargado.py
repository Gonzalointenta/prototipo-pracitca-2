# -*- coding: utf-8 -*-
"""
interfaz_encargado.py — paneles exclusivos de la vista de encargado. Los usan
tanto app.py (web) como app_encargado.py (escritorio, corte local), para que
un arreglo o mejora quede disponible en ambas sin mantener dos copias.
"""

import os
from datetime import timedelta

import pandas as pd
import streamlit as st

import core
import formato_impresion
import interfaz_comun
from interfaz_comun import boton_descargar_archivo, boton_imprimir

# CARPETA_PDF se referencia como interfaz_comun.CARPETA_PDF (no "from ... import
# CARPETA_PDF") a propósito: app_encargado.py la reasigna después de importar
# este módulo (para guardar los PDF en la carpeta de datos local en vez de al
# lado del ejecutable), y un "from X import NOMBRE" congela el valor de ese
# momento — no vería la reasignación posterior. Ver el mismo problema resuelto
# en core.py con DB_PATH.


def panel_solicitudes_activas():
    cab_izq, cab_der = st.columns([4, 1])
    cab_izq.subheader("Solicitudes por procesar")
    # Botón para recargar y ver si entraron solicitudes nuevas desde la web
    # sin tener que cambiar de pestaña. Solo fuerza un rerun: la lista de
    # activas NO está cacheada (se relee de la base en cada corrida), así que
    # con esto aparece lo que se haya creado recién.
    if cab_der.button("🔄 Actualizar", width='stretch',
                      help="Recarga para ver solicitudes nuevas recién ingresadas."):
        st.rerun()
    st.caption(
        "Solo las pendientes. Al cerrar o anular una solicitud, esta sale de la pantalla "
        "y queda disponible en Pedidos completados y en el Historial."
    )

    # Comprobante de lo recién cerrado, antes de cualquier salida temprana.
    if st.session_state.get("folio_recien_cerrado"):
        st.success("Solicitud cerrada — stock descontado. Imprima el comprobante para que "
                   "quien retira firme la recepción.")
        boton_imprimir(st.session_state.folio_recien_cerrado,
                       sufijo_key="cierre", solo_comprobante=True)
        if st.button("Listo"):
            st.session_state.folio_recien_cerrado = None
            st.rerun()
        st.divider()

    atrasadas = core.contar_solicitudes_atrasadas()
    if atrasadas:
        st.error(f"⚠️ {atrasadas} solicitud(es) pendientes vienen de jornadas anteriores "
                 "— proceso tardado.")

    df_activas = core.listar_solicitudes_activas()
    if df_activas.empty:
        st.success("No hay solicitudes pendientes.")
        return

    df_vista = df_activas.copy()
    df_vista.insert(0, "", df_vista["atrasada"].map({True: "⚠️", False: ""}))
    df_vista["estado"] = df_vista["estado"].map(ETIQUETAS_ESTADO).fillna(df_vista["estado"])
    df_vista = df_vista.rename(columns={"correlativo": "N°", "n_productos": "productos",
                                        "area_departamento": "departamento"})

    def _resaltar(fila):
        return ["background-color: rgba(255,0,0,0.12)" if fila["atrasada"] else ""] * len(fila)

    st.dataframe(
        df_vista.style.apply(_resaltar, axis=1),
        width='stretch', hide_index=True,
        column_config={"atrasada": None, "folio": None, "fecha_solicitud": "fecha"},
    )
    if atrasadas:
        st.caption("⚠️ = pendiente arrastrada de una jornada anterior.")

    # ------------------------------------------------------------- procesar
    st.divider()
    st.subheader("Procesar una solicitud")

    n = st.session_state.proceso_nonce
    etiquetas = {f'N° {f.correlativo} · {f.solicitante} · {f.area_departamento}': f.folio
                 for f in df_activas.itertuples()}
    # El aviso de la acción anterior se muestra ACÁ, antes de exigir que haya
    # una solicitud elegida. Si se mostrara más abajo, quedaba esperando y
    # reaparecía recién al abrir la solicitud siguiente, dando a entender que
    # era esa la que se había anulado.
    if st.session_state.get("aviso_proceso"):
        st.success(st.session_state.aviso_proceso)
        st.session_state.aviso_proceso = None

    elegido = st.selectbox("Elegir solicitud", [""] + list(etiquetas.keys()),
                           key=f"folio_select_{n}")
    if not elegido:
        return
    folio = etiquetas[elegido]

    df = core.resumen_solicitud(folio)
    if df.empty:
        st.error("Solicitud no encontrada.")
        return
    estado = df.iloc[0]["estado"]
    st.info(f"Estado: **{ETIQUETAS_ESTADO.get(estado, estado)}**")

    def salir_del_proceso(mensaje=None):
        """Cierra el detalle y vuelve a la lista: lo demás se ve en el Historial."""
        if mensaje:
            st.session_state.aviso_proceso = mensaje
        st.session_state.folio_preparando = None
        st.session_state.proceso_nonce += 1
        st.rerun()

    # ---- paso 1: esperando el papel firmado
    if estado == "pendiente_firma":
        st.dataframe(
            df[["producto", "cantidad_solicitada", "mensaje_sistema"]].rename(
                columns={"cantidad_solicitada": "solicitado", "mensaje_sistema": "observación"}),
            width='stretch', hide_index=True,
        )
        if st.button("El solicitante trajo el papel timbrado y firmado", type="primary"):
            core.aceptar_preliminar(folio)
            st.rerun()

    # ---- paso 2: ajustar cantidades (una sola tabla editable)
    elif estado in ("preliminar_aceptada", "editada"):
        st.write("Ajuste lo realmente entregado:")
        st.caption("Deje en 0 lo que no se entregue: no aparecerá en el comprobante.")
        cantidades = {}
        for _, fila in df.iterrows():
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{fila['producto']}**"
                        + (f"  \n{fila['mensaje_sistema']}" if fila["mensaje_sistema"] else ""))
            # cantidad_entregada aún NULL la lee pandas como None o NaN; en
            # ambos casos se arranca desde lo solicitado. Se usa pd.isna (no
            # solo `is None`) porque un NaN no es None y hacía reventar int().
            base = fila["cantidad_entregada"]
            if base is None or pd.isna(base):
                base = fila["cantidad_solicitada"]
            cantidades[fila["producto"]] = c2.number_input(
                f"entregado — {fila['producto']}", min_value=0, step=1,
                value=core.formatear_cantidad(base),
                key=f"ent_{n}_{fila['producto']}", label_visibility="collapsed",
            )

        def guardar_cantidades():
            conn = core.get_connection()
            for producto, cantidad in cantidades.items():
                codigo = conn.execute(
                    "SELECT codigo FROM productos WHERE nombre_estandar=?", (producto,)
                ).fetchone()[0]
                core.editar_entrega(folio, codigo, cantidad)
            conn.close()

        # Si no queda nada por entregar, la solicitud pierde sentido: se
        # advierte y se resalta el botón de anular. No se bloquea el guardado
        # porque a veces conviene dejar constancia de que no había stock.
        todo_en_cero = bool(cantidades) and all(v == 0 for v in cantidades.values())
        if todo_en_cero:
            st.session_state.pedido_vacio = folio
            st.error(
                "**Se han retirado todos los insumos del pedido solicitado.** "
                "Se recomienda anular el pedido."
            )
        else:
            st.session_state.pedido_vacio = None

        c1, c2 = st.columns(2)
        if c1.button("Guardar y salir", width='stretch'):
            guardar_cantidades()
            salir_del_proceso("Cantidades guardadas. Puede retomarlas cuando quiera.")

        if c2.button("Guardar y preparar comprobante", type="primary", width='stretch'):
            guardar_cantidades()
            st.session_state.folio_preparando = folio
            st.rerun()

        # ---- paso 3: comprobante primero, descuento de stock al final
        #
        # El descuento se dejó para el último paso a propósito: así el
        # encargado revisa el documento y corrige el texto ANTES de que el
        # movimiento quede firme. Si algo está mal, todavía puede volver
        # atrás sin haber tocado el inventario.
        if st.session_state.get("folio_preparando") == folio:
            st.divider()
            st.subheader("Comprobante de la entrega")
            st.caption(
                "Revise el documento y su texto. El stock **todavía no se ha descontado**: "
                "eso ocurre recién al confirmar más abajo."
            )
            boton_imprimir(folio, sufijo_key="previo", solo_comprobante=True)

            st.divider()
            c1, c2 = st.columns(2)
            if c1.button("Volver a corregir cantidades", width='stretch'):
                st.session_state.folio_preparando = None
                st.rerun()
            if c2.button("Confirmar entrega y descontar stock", type="primary",
                         width='stretch'):
                alertas = core.cerrar_solicitud(
                    folio, usuario_operacion=core.nombre_encargado())
                st.session_state.folio_recien_cerrado = folio
                st.session_state.folio_preparando = None
                for _codigo, tipo, mensaje in alertas:
                    st.session_state.aviso_proceso = f"[{tipo.upper()}] {mensaje}"
                salir_del_proceso()

    # ---- anular, disponible mientras no esté cerrada
    vacio = st.session_state.get("pedido_vacio") == folio
    with st.expander("Anular esta solicitud", expanded=vacio):
        motivo = st.text_input("Motivo de anulación", key=f"motivo_{n}",
                               value="No había stock disponible" if vacio else "")
        if vacio:
            st.markdown('<div class="pedido-vacio">', unsafe_allow_html=True)
        anular = st.button("Anular solicitud")
        if vacio:
            st.markdown('</div>', unsafe_allow_html=True)
        if anular:
            if not motivo:
                st.warning("Escriba un motivo antes de anular.")
            else:
                core.anular_solicitud(folio, motivo)
                salir_del_proceso("Solicitud anulada.")


def pesos(valor) -> str:
    """Formatea un número como pesos chilenos: 25487911 -> '$25.487.911'."""
    return f"${valor:,.0f}".replace(",", ".")


def panel_inventario_general():
    st.subheader("Inventario general")
    total = core.valor_total_inventario()
    st.metric("Valor de la totalidad de los bienes", pesos(total))
    st.caption("Suma de 'SALDO VAL.' del último corte importado desde SMC, tal como está impreso en el listado.")

    df = core.listar_inventario_general()

    # Buscador visible de entrada, sin tener que abrir el ícono de lupa
    # de la tabla. Filtra por nombre, código o categoría a la vez.
    filtro = st.text_input("Buscar en el inventario", placeholder="nombre, código o categoría")
    if filtro:
        f = core.normalizar(filtro)
        mask = (
            df["nombre_estandar"].apply(lambda x: f in core.normalizar(str(x)))
            | df["codigo"].apply(lambda x: f in core.normalizar(str(x)))
            | df["categoria"].apply(lambda x: f in core.normalizar(str(x)))
        )
        df = df[mask]
        st.caption(f"{len(df)} producto(s) coinciden con \"{filtro}\".")

    # Los valores se muestran como dinero, no como enteros pelados.
    df_vista = df.copy()
    df_vista["valor_saldo"] = df_vista["valor_saldo"].apply(pesos)
    df_vista = df_vista.rename(columns={
        "nombre_estandar": "producto", "unidad_medida": "unidad",
        "valor_saldo": "valor total",
    })
    st.dataframe(df_vista, width='stretch', hide_index=True)


def panel_inventario_critico():
    st.subheader("Inventario crítico")
    st.caption("Insumos agotados o bajo su stock crítico — los que requieren compra o renovación más urgente.")
    df = core.listar_stock_critico()
    if df.empty:
        st.success("No hay productos agotados ni bajo su stock crítico.")
    else:
        st.dataframe(df, width='stretch', hide_index=True)


ETIQUETAS_ESTADO = {
    "pendiente_firma": "Pendiente de firma",
    "preliminar_aceptada": "Aceptada preliminar",
    "editada": "Editada en bodega",
    "cerrada": "Cerrada / entregada",
    "anulada": "Anulada",
}


def panel_historial():
    st.subheader("Historial de solicitudes")
    st.caption(
        "Buscador y filtros sobre todas las solicitudes registradas. Desde acá se pueden "
        "reimprimir comprobantes y armar recopilaciones (por ejemplo, todos los movimientos "
        "de un día o de una semana) juntando de a dos por hoja."
    )

    # ---------------------------------------------------------------- filtros
    c1, c2, c3 = st.columns(3)
    agrupacion = c1.selectbox("Agrupar por", ["día", "semana", "mes", "año"], index=2)
    # Por defecto se acota a este mes: con miles de solicitudes históricas,
    # cargar "Todo" y desplegar cada una haría la pantalla inusable.
    rango = c2.selectbox(
        "Rango", ["Este mes", "Hoy", "Últimos 7 días", "Este año", "Personalizado", "Todo"],
        index=0,
    )
    estados = c3.multiselect(
        "Estado", ["pendiente_firma", "preliminar_aceptada", "editada", "cerrada", "anulada"],
        default=[],
    )

    hoy = core.hoy_chile()
    desde = hasta = None
    if rango == "Hoy":
        desde = hasta = hoy
    elif rango == "Últimos 7 días":
        desde, hasta = hoy - timedelta(days=6), hoy
    elif rango == "Este mes":
        desde, hasta = hoy.replace(day=1), hoy
    elif rango == "Este año":
        desde, hasta = hoy.replace(month=1, day=1), hoy
    elif rango == "Personalizado":
        cd, ch = st.columns(2)
        desde = cd.date_input("Desde", value=hoy - timedelta(days=30))
        hasta = ch.date_input("Hasta", value=hoy)

    f1, f2, f3 = st.columns(3)
    solicitante = f1.text_input("Usuario / solicitante", placeholder="parte del nombre")
    area = f2.text_input("Departamento", placeholder="ej. finanzas")
    oficina = f3.text_input("Oficina", placeholder="ej. archivo")

    producto = st.text_input(
        "Producto", placeholder="nombre registrado en el sistema o código, ej. RESMA o 00101001",
        help="Muestra solo las solicitudes que incluyeron ese insumo.",
    )

    o1, o2 = st.columns([2, 1])
    ordenar_por = o1.selectbox(
        "Ordenar por",
        ["Fecha", "N° de solicitud", "Solicitante", "Departamento", "Oficina",
         "Cantidad de productos", "Unidades"],
    )
    descendente = o2.selectbox("Orden", ["Mayor a menor", "Menor a mayor"]) == "Mayor a menor"

    df = core.historial_filtrado(
        desde=desde, hasta=hasta, solicitante=solicitante, area=area,
        oficina=oficina, estados=estados or None, producto=producto,
    )

    if df.empty:
        st.info("No hay solicitudes que coincidan con los filtros.")
        return

    columnas_orden = {
        "Fecha": "fecha_solicitud", "N° de solicitud": "correlativo",
        "Solicitante": "solicitante", "Departamento": "area_departamento",
        "Oficina": "oficina", "Cantidad de productos": "n_productos",
        "Unidades": "total_unidades",
    }
    df = df.sort_values(columnas_orden[ordenar_por], ascending=not descendente)

    df, resumen = core.agrupar_historial(df, agrupacion)

    m1, m2, m3 = st.columns(3)
    m1.metric("Solicitudes", len(df))
    m2.metric("Líneas de producto", int(df["n_productos"].sum()))
    m3.metric("Unidades", int(df["total_unidades"].sum()))

    st.markdown(f"**Resumen por {agrupacion}**")
    st.dataframe(resumen, width='stretch', hide_index=True)

    # --------------------------------------------------- exportar a Excel
    st.divider()
    st.markdown("**Exportar historial a Excel**")
    st.caption(
        "Genera un Excel a partir de los COMPROBANTES ENTREGADOS (solo solicitudes cerradas, "
        "con la cantidad realmente entregada, no la solicitada) — es lo más preciso porque "
        "incluye los ajustes o rechazos que haga el encargado en bodega. Queda listo para armar "
        "tablas dinámicas: en Excel, Insertar → Tabla dinámica, usando la hoja 'Detalle' como "
        "origen. Se recomienda actualizarlo cada 5 horas de uso — el botón sobrescribe siempre "
        "el mismo archivo, no genera uno nuevo cada vez. No incluye los PDF de solicitud/"
        "comprobante (inflarían mucho el archivo), solo el nombre del archivo correspondiente "
        "dentro de la carpeta de formularios."
    )

    horas_export = core.horas_desde_ultimo_export_excel()
    ultima_export = core.leer_config("ultima_generacion_excel_historial")
    ce1, ce2 = st.columns([1, 2])
    ce1.metric("Última generación", ultima_export if ultima_export else "nunca")
    with ce2:
        hora_actual = core.ahora_chile().hour
        dentro_jornada = core.HORA_INICIO_JORNADA <= hora_actual < core.HORA_CIERRE_JORNADA
        if horas_export is None or horas_export >= core.HORAS_ENTRE_EXPORTES_EXCEL:
            if dentro_jornada:
                st.warning(
                    "Ya pasaron 5 horas de jornada (o nunca se ha generado): conviene "
                    "actualizar el Excel."
                )
        else:
            st.success(f"Al día: se generó hace {horas_export:.1f} horas.")

    if st.button("Generar / actualizar Excel del historial", width='stretch'):
        with st.spinner("Generando…"):
            core.exportar_historial_excel()
        st.success("Excel actualizado.")

    if os.path.exists(core.RUTA_EXCEL_HISTORIAL):
        nombre_excel = os.path.basename(core.RUTA_EXCEL_HISTORIAL)
        boton_descargar_archivo(
            core.RUTA_EXCEL_HISTORIAL, f"ABRIR «{nombre_excel}»",
            nombre_archivo=nombre_excel, key="descargar_excel_historial",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption(f"Está en el Escritorio como «{nombre_excel}» — es siempre el mismo "
                   "archivo, se actualiza en su lugar cada vez que lo genera.")

    # ------------------------------------------------- recopilador de impresión
    st.divider()
    st.markdown("**Recopilar e imprimir**")
    periodos = resumen["periodo"].tolist()
    periodo_sel = st.selectbox("Período a recopilar", ["(toda la selección)"] + periodos)

    df_imprimir = df if periodo_sel == "(toda la selección)" else df[df["periodo"] == periodo_sel]
    cerradas = df_imprimir[df_imprimir["estado"] == "cerrada"]

    st.caption(
        f"{len(df_imprimir)} solicitud(es) en la selección · {len(cerradas)} cerrada(s) "
        "con comprobante disponible."
    )

    if cerradas.empty:
        st.info("No hay solicitudes cerradas en esta selección para imprimir comprobantes.")
    else:
        comprobantes = [core.datos_para_impresion(f) for f in cerradas["folio"]]
        n_chicos = sum(1 for _, items in comprobantes
                       if formato_impresion.cabe_en_media_hoja(items))
        n_grandes = len(comprobantes) - n_chicos
        hojas = (n_chicos + 1) // 2 + n_grandes
        ahorro = len(comprobantes) - hojas

        st.caption(f"{len(comprobantes)} comprobante(s) → **{hojas} hoja(s)**"
                   + (f", ahorrando {ahorro}" if ahorro > 0 else ""))

        ruta = interfaz_comun.CARPETA_PDF / "recopilacion_comprobantes.pdf"
        formato_impresion.generar_comprobantes_pareados_pdf(ruta, comprobantes)
        boton_descargar_archivo(
            ruta, "Imprimir compilado de comprobantes seleccionados",
            nombre_archivo=f"comprobantes_{str(periodo_sel).replace('/', '-').replace(' ', '_')}.pdf",
            mime="application/pdf", key="compilado_historial",
        )

    # ------------------------------------------------------------- el detalle
    st.divider()
    st.markdown("**Solicitudes**")

    # Paginación: no se despliega el detalle de todo el historial de una vez.
    # Con más de mil solicitudes acumuladas, dibujar cada una dejaría la
    # página inutilizable; se muestran de a POR_PAGINA y se navega.
    POR_PAGINA = 25
    detalle_periodos = ([periodo_sel] if periodo_sel != "(toda la selección)"
                        else resumen["periodo"].tolist())
    df_detalle = df[df["periodo"].isin(detalle_periodos)]

    total_paginas = max(1, (len(df_detalle) + POR_PAGINA - 1) // POR_PAGINA)
    if total_paginas > 1:
        pagina = st.number_input(
            f"Página (de {total_paginas}) — {len(df_detalle)} solicitudes en la selección",
            min_value=1, max_value=total_paginas, value=1, step=1,
        )
    else:
        pagina = 1
    inicio = (int(pagina) - 1) * POR_PAGINA
    df_pagina = df_detalle.iloc[inicio:inicio + POR_PAGINA]

    for periodo in detalle_periodos:
        grupo = df_pagina[df_pagina["periodo"] == periodo]
        if grupo.empty:
            continue
        st.markdown(f"##### {periodo}  ·  {len(grupo)} en esta página")
        for _, fila in grupo.iterrows():
            etiqueta = (f'N° {fila["correlativo"]}  ·  {fila["solicitante"]}  ·  '
                        f'{fila["fecha_solicitud"]}')
            with st.expander(etiqueta):
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"**Departamento**  \n{fila['area_departamento'] or '—'}")
                c2.markdown(f"**Oficina**  \n{fila['oficina'] or '—'}")
                c3.markdown(f"**Supervisor**  \n{fila['supervisor'] or '—'}")
                c4.markdown(f"**Estado**  \n{ETIQUETAS_ESTADO.get(fila['estado'], fila['estado'])}")

                detalle = core.detalle_folio(fila["folio"])
                st.dataframe(
                    detalle.rename(columns={
                        "nombre_estandar": "producto", "unidad_medida": "unidad",
                        "cantidad_solicitada": "solicitado", "cantidad_entregada": "entregado",
                        "mensaje_sistema": "observación",
                    }),
                    width='stretch', hide_index=True,
                )
                # Reimpresión: útil cuando piden revisiones o se extravía el papel
                if fila["estado"] == "cerrada":
                    boton_imprimir(fila["folio"], sufijo_key=f"hist_{fila['correlativo']}",
                                   solo_comprobante=True, editable=False)


def panel_crear_alias():
    st.subheader("Crear un nuevo alias para producto existente")
    st.caption(
        "Un alias NO cambia el nombre del producto. Solo agrega otra forma de escribirlo en el "
        "buscador: si registra 'confort' para ROLLO PAPEL HIGIÉNICO, quien escriba 'confort' "
        "encontrará ese producto. Lo hace el encargado porque es quien sabe cómo le dicen "
        "realmente a cada cosa."
    )

    st.markdown("**1. Código del producto**")
    codigo = st.text_input("Código", placeholder="ej. 00204001", key="alias_codigo")

    producto = core.obtener_producto(codigo) if codigo.strip() else None

    if codigo.strip() and producto is None:
        st.error(f'No existe ningún producto activo con el código "{codigo.strip()}".')
        st.caption("Puede buscar el código correcto en la pestaña Inventario general.")

    if producto:
        st.markdown("**2. Corroboración del producto registrado en sistema**")
        st.success(
            f"**{producto['nombre_estandar']}**  \n"
            f"Categoría: {producto['categoria']} · Unidad: {producto['unidad_medida']} · "
            f"Saldo actual: {producto['saldo']}"
        )
        df_alias = core.alias_de_producto(producto["codigo"])
        if not df_alias.empty:
            st.markdown("**Alias registrados para este producto**")
            st.caption("Puede corregir el texto de cualquiera o eliminarlo.")
            for _, fila_alias in df_alias.iterrows():
                ca, cb, cc = st.columns([6, 2, 1])
                nuevo_texto = ca.text_input(
                    "alias", value=fila_alias["texto_alias"],
                    key=f"ed_{fila_alias['id']}", label_visibility="collapsed",
                )
                if cb.button("Guardar", key=f"btn_ed_{fila_alias['id']}"):
                    ok, mensaje = core.editar_alias(int(fila_alias["id"]), nuevo_texto)
                    (st.success if ok else st.error)(mensaje)
                    if ok:
                        st.rerun()
                if cc.button("✕", key=f"btn_del_{fila_alias['id']}",
                             help=f'Eliminar el alias "{fila_alias["texto_alias"]}"'):
                    ok, mensaje = core.eliminar_alias(int(fila_alias["id"]))
                    (st.success if ok else st.error)(mensaje)
                    if ok:
                        st.rerun()

        st.markdown("**3. Escribir el nuevo alias**")
        nuevo_alias = st.text_input(
            "Nuevo alias", placeholder="ej. confort", key="alias_texto"
        )
        if st.button("Registrar alias"):
            ok, mensaje = core.crear_alias_manual(producto["codigo"], nuevo_alias)
            if ok:
                st.success(mensaje)
            else:
                st.error(mensaje)

    st.divider()
    st.subheader("Carga masiva desde Excel")
    st.caption(
        "Si prefiere anotar los alias en un Excel a mano, súbalo aquí. El archivo debe tener "
        "dos columnas llamadas 'codigo' y 'alias' — una fila por cada forma en que la gente "
        "nombra un producto. Se procesa fila por fila y se muestra qué entró y qué no."
    )

    ejemplo = pd.DataFrame({
        "codigo": ["00204001", "00204001", "00205033"],
        "alias": ["confort", "papel confort", "poet"],
    })
    with st.expander("Ver formato esperado del Excel"):
        st.dataframe(ejemplo, width='stretch', hide_index=True)

    archivo = st.file_uploader("Archivo de alias (.xlsx o .csv)", type=["xlsx", "csv"])
    if archivo is not None and st.button("Procesar archivo"):
        try:
            resultados = core.importar_alias_desde_excel(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
        else:
            if resultados.empty:
                st.warning("El archivo no traía filas con datos.")
            else:
                creados = (resultados["resultado"] == "creado").sum()
                rechazados = (resultados["resultado"] == "rechazado").sum()
                c1, c2 = st.columns(2)
                c1.metric("Alias creados", int(creados))
                c2.metric("Filas rechazadas", int(rechazados))
                st.dataframe(resultados, width='stretch', hide_index=True)
                if rechazados:
                    st.caption("Revise la columna 'detalle' para ver por qué se rechazó cada fila.")

    st.divider()
    st.subheader("Búsquedas sin resultado (referencia)")
    st.caption(
        "Textos que alguien buscó y no encontraron nada. Sirven de pista sobre qué alias "
        "conviene crear, pero no hacen nada por sí solos."
    )
    conn = core.get_connection()
    df_pend = pd.read_sql("SELECT * FROM alias_pendientes WHERE revisado=0 ORDER BY id DESC", conn)
    conn.close()
    if df_pend.empty:
        st.info("No hay búsquedas sin resultado registradas.")
    else:
        st.dataframe(df_pend, width='stretch', hide_index=True)


def panel_pedidos_completados():
    st.subheader("Pedidos completados")
    st.caption(
        "Comprobantes de solicitudes cerradas en la jornada vigente (desde las 19:00 del día "
        "anterior). Pasadas las 19:00 esta lista se vacía y arranca de nuevo — lo cerrado en "
        "jornadas anteriores no desaparece, queda disponible siempre en el Historial. Puede "
        "imprimirlos de a dos por hoja: se juntan respetando el formato, con una línea de "
        "corte al medio, para no gastar una hoja entera en pedidos chicos."
    )

    df = core.pedidos_completados_jornada()

    if df.empty:
        st.info("Todavía no hay solicitudes cerradas en esta jornada.")
        return

    # se marca cuáles caben en media hoja, para que la elección sea informada
    filas = []
    for _, fila in df.iterrows():
        _, items = core.datos_para_impresion(fila["folio"])
        filas.append({
            "N°": fila["correlativo"], "folio": fila["folio"],
            "fecha": fila["fecha_solicitud"], "solicitante": fila["solicitante"],
            "área": fila["area_departamento"], "productos": len(items),
            "media hoja": "sí" if formato_impresion.cabe_en_media_hoja(items) else "no (va sola)",
        })
    df_vista = pd.DataFrame(filas)
    st.dataframe(df_vista.drop(columns=["folio"]), width='stretch', hide_index=True)

    st.markdown("**Imprimir varios en una sola hoja**")
    opciones = {f'N° {f["N°"]} · {f["solicitante"]} ({f["productos"]} prod.)': f["folio"]
                for f in filas}
    st.info(
        "Para imprimir un solo comprobante desde esta ventana, selecciónelo en la lista y "
        "luego haga clic en cualquier espacio en blanco de la página: el botón de impresión "
        "aparecerá debajo."
    )
    elegidos = st.multiselect(
        "Elija los comprobantes a imprimir juntos", list(opciones.keys()),
        help="Se agrupan de a dos por hoja. Los que no caben en media hoja salen solos.",
    )

    if elegidos:
        comprobantes = [core.datos_para_impresion(opciones[e]) for e in elegidos]
        n_chicos = sum(1 for _, items in comprobantes
                       if formato_impresion.cabe_en_media_hoja(items))
        n_grandes = len(comprobantes) - n_chicos
        hojas = (n_chicos + 1) // 2 + n_grandes
        st.caption(f"{len(comprobantes)} comprobante(s) → **{hojas} hoja(s)**"
                   + (f" ({n_grandes} van solas por tamaño)" if n_grandes else ""))

        ruta = interfaz_comun.CARPETA_PDF / "comprobantes_agrupados.pdf"
        formato_impresion.generar_comprobantes_pareados_pdf(ruta, comprobantes)
        boton_descargar_archivo(
            ruta, "Imprimir compilado de comprobantes seleccionados",
            nombre_archivo="comprobantes_agrupados.pdf", mime="application/pdf",
            key="compilado_pedidos_completados",
        )


def panel_importar_saldos():
    st.subheader("Actualizar saldos desde SMC")

    corte = core.fecha_ultimo_corte()
    horas = core.horas_desde_ultima_importacion()
    pendiente_semana = core.actualizacion_semanal_pendiente()
    if corte:
        c1, c2 = st.columns([2, 3])
        c1.metric("Último saldo importado desde SMC", str(corte)[:16])
        with c2:
            if pendiente_semana:
                # queda marcado acá aunque se haya cerrado el aviso de arriba
                st.error(
                    "⚠️ **Pendiente esta semana.** Todavía no se importa el listado de SMC "
                    "desde el lunes — corresponde escanearlo y actualizarlo."
                )
            else:
                st.success(f"Al día: importado hace {horas:.1f} horas, dentro de esta semana.")
    else:
        st.warning(
            "Todavía no se ha importado ningún saldo desde SMC. Los saldos que se muestran "
            "son los del catálogo inicial (corte 24/07/2026)."
        )

    st.caption(
        "SMC es el sistema oficial del stock; esta web no lo es. Entre una importación y la "
        "siguiente, el saldo que se ve acá es una estimación: el del último corte menos lo "
        "que se entregó desde esta web. No incluye compras, devoluciones ni ajustes hechos "
        "directamente en SMC — por eso conviene importar cada vez que llegue mercadería."
    )

    with st.expander("¿Por qué esto no puede dañar el inventario real de SMC?"):
        st.markdown(
            "- Hacia **SMC** este sistema envía solo **movimientos** "
            "(\"salieron 2 unidades del código X\"), nunca un saldo total. "
            "Si se compran 300 rollos y se registran en SMC, ese ingreso queda intacto: "
            "el movimiento de salida simplemente se resta encima.\n"
            "- Desde **SMC** este sistema **recibe** el saldo y reemplaza su estimación. "
            "Ante cualquier diferencia, gana SMC.\n"
            "- Por eso la web nunca sobrescribe el inventario real, y cualquier desvío se "
            "corrige solo en la siguiente importación."
        )

    archivo = st.file_uploader(
        "Archivo de saldos exportado desde SMC (.xlsx o .csv)", type=["xlsx", "csv"],
        key="upload_saldos",
    )
    st.caption(
        "Debe traer al menos las columnas 'codigo' y 'saldo'; opcionalmente 'stock_critico' y "
        "'valor_saldo' (el 'SALDO VAL.' del listado, en pesos)."
    )

    if archivo is not None and st.button("Importar saldos", type="primary"):
        try:
            diferencias, n = core.importar_saldos_smc(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
        else:
            st.success(f"{n} producto(s) actualizados con el saldo real de SMC.")
            if diferencias.empty:
                st.info("No había diferencias: la estimación local coincidía con SMC.")
            else:
                st.markdown("**Diferencias detectadas**")
                st.caption(
                    "Son movimientos que ocurrieron fuera de esta web (compras, devoluciones, "
                    "ajustes o entregas registradas directo en SMC). Ya quedaron corregidos."
                )
                st.dataframe(diferencias, width='stretch', hide_index=True)
            st.rerun()

    # --------------------------------------------- listado escaneado (PDF)
    st.divider()
    st.markdown("**Subir el listado escaneado (PDF)**")
    st.caption(
        "Para cuando SMC solo se puede imprimir en papel: escanee el 'Listado de Saldos "
        "Artículos' y suba el PDF acá. El sistema lee los códigos y saldos con reconocimiento "
        "óptico (OCR) — como leer un escaneo puede confundir algún dígito, la lectura NUNCA se "
        "aplica sola: primero se revisa en pantalla, se corrige lo que haga falta, y solo "
        "después se aplica al inventario. Esta lectura solo actualiza el SALDO (cantidad); "
        "el 'SALDO VAL.' en pesos no se toca acá, así que 'Valor de la totalidad de los "
        "bienes' se mantiene como el del último catálogo cargado hasta que se actualice ese "
        "catálogo con un nuevo listado completo."
    )

    archivo_pdf = st.file_uploader("PDF escaneado del listado de SMC", type=["pdf"], key="upload_pdf_smc")
    if archivo_pdf is not None and st.button("Leer PDF (OCR)"):
        with st.spinner("Leyendo el PDF… puede tardar unos segundos por página."):
            try:
                st.session_state["df_ocr_saldos"] = core.extraer_saldos_pdf_escaneado(archivo_pdf)
            except Exception as e:
                st.session_state["df_ocr_saldos"] = None
                st.error(
                    f"No se pudo leer el PDF: {e}. Si el error menciona 'tesseract', el motor de "
                    "OCR no está instalado en este entorno."
                )

    df_ocr = st.session_state.get("df_ocr_saldos")
    if df_ocr is not None and not df_ocr.empty:
        n_revisar = int(df_ocr["revisar"].sum())
        m1, m2 = st.columns(2)
        m1.metric("Filas leídas", len(df_ocr))
        m2.metric("Necesitan revisión", n_revisar)
        if n_revisar:
            st.warning(
                f"⚠️ {n_revisar} fila(s) quedaron arriba de la tabla, marcadas en la columna "
                "'revisar': código que no calzó exacto con el catálogo, saldo que no se pudo "
                "leer, o un cambio de magnitud/signo inusual frente al saldo actual. Corrija el "
                "código o el saldo directamente en la tabla, o destilde 'aplicar' para "
                "descartar esa fila."
            )
        else:
            st.success("Todas las filas calzaron exacto con el catálogo — igual conviene revisar antes de aplicar.")

        st.caption(
            "'saldo_leido' es editable: corrija ahí si el OCR se equivocó. 'saldo_actual_sistema' "
            "es lo que hoy tiene el sistema, para comparar."
        )
        df_editado = st.data_editor(
            df_ocr,
            width='stretch', hide_index=True, key="editor_ocr_saldos",
            column_order=["revisar", "aplicar", "pagina", "codigo", "codigo_leido",
                          "producto", "saldo_leido", "saldo_actual_sistema"],
            column_config={
                "revisar": st.column_config.CheckboxColumn("revisar", disabled=True),
                "aplicar": st.column_config.CheckboxColumn("aplicar"),
                "pagina": st.column_config.NumberColumn("pág.", disabled=True),
                "codigo_leido": st.column_config.TextColumn("leído del PDF", disabled=True),
                "producto": st.column_config.TextColumn("producto", disabled=True),
                "saldo_actual_sistema": st.column_config.NumberColumn("saldo actual", disabled=True),
            },
        )

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("Aplicar al inventario", type="primary"):
                diferencias, n = core.aplicar_saldos_revisados(df_editado)
                # OJO: sin st.rerun() acá a propósito — de lo contrario el
                # mensaje de éxito y la tabla de diferencias desaparecen
                # antes de que el encargado alcance a verlos.
                st.session_state["df_ocr_saldos"] = None
                st.success(f"{n} producto(s) actualizados con el saldo leído del PDF.")
                if not diferencias.empty:
                    st.markdown("**Diferencias detectadas**")
                    st.dataframe(diferencias, width='stretch', hide_index=True)
        with c2:
            if st.button("Descartar esta lectura"):
                st.session_state["df_ocr_saldos"] = None
                st.rerun()
    elif df_ocr is not None:
        st.info("No se detectó ninguna fila reconocible en el PDF.")


def panel_estadisticas():
    st.subheader("Estadísticas de consumo")
    st.caption(
        "Quién consume y qué se consume. Se calcula sobre las solicitudes cerradas, usando "
        "la cantidad realmente entregada. El valor en pesos usa el valor unitario fijado en "
        "el último corte (valor total del saldo ÷ cantidad), descontado por cada entrega."
    )

    hoy = core.hoy_chile()
    c1, c2, c3 = st.columns(3)
    rango = c1.selectbox(
        "Período", ["Este año", "Últimos 12 meses", "Este mes", "Todo", "Personalizado"],
        index=0, key="rango_stats",
    )
    metrica = c2.selectbox("Medir por", ["unidades", "solicitudes", "valor en pesos"], index=0)
    top_n = c3.slider("Cuántos mostrar", 5, 20, 10)

    desde = hasta = None
    if rango == "Este año":
        desde, hasta = hoy.replace(month=1, day=1), hoy
    elif rango == "Últimos 12 meses":
        desde, hasta = hoy - timedelta(days=365), hoy
    elif rango == "Este mes":
        desde, hasta = hoy.replace(day=1), hoy
    elif rango == "Personalizado":
        cd, ch = st.columns(2)
        desde = cd.date_input("Desde", value=hoy - timedelta(days=180), key="stats_desde")
        hasta = ch.date_input("Hasta", value=hoy, key="stats_hasta")

    datos = core.estadisticas_consumo(desde=desde, hasta=hasta)
    columna = {"unidades": "unidades", "solicitudes": "solicitudes",
               "valor en pesos": "valor"}[metrica]

    if datos["departamento"].empty:
        st.info("No hay solicitudes cerradas en este período.")
        return

    def _miles(n):
        return f"{int(n):,}".replace(",", ".")

    # ------------------------------------------------------------------ KPIs
    total_sol = int(datos["departamento"]["solicitudes"].sum())
    total_uni = int(datos["departamento"]["unidades"].sum())
    total_val = int(datos["departamento"]["valor"].sum()) if "valor" in datos["departamento"] else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Solicitudes entregadas", _miles(total_sol))
    k2.metric("Unidades entregadas", _miles(total_uni))
    k3.metric("Valor entregado", f"${_miles(total_val)}")

    def _grafico(df, etiqueta, titulo, ayuda=None):
        if df.empty or columna not in df:
            st.info(f"Sin datos para {titulo.lower()}.")
            return
        st.markdown(f"**{titulo}**")
        if ayuda:
            st.caption(ayuda)
        top = df.nlargest(top_n, columna)[[etiqueta, columna]].set_index(etiqueta)
        st.bar_chart(top, horizontal=True, height=min(60 + 28 * len(top), 620))
        with st.expander("Ver la tabla"):
            tabla = df.nlargest(top_n, columna).copy()
            st.dataframe(tabla, width='stretch', hide_index=True)

    st.divider()
    _grafico(datos["departamento"], "departamento",
             f"Departamentos que más solicitan (por {metrica})")

    st.divider()
    _grafico(datos["producto"], "producto",
             f"Productos más solicitados (por {metrica})")

    st.divider()
    _grafico(datos["solicitante"], "solicitante",
             f"Personas que más solicitan (por {metrica})")

    st.divider()
    _grafico(datos["oficina"], "oficina", f"Oficinas que más solicitan (por {metrica})")

    st.divider()
    _grafico(datos["categoria"], "categoria", f"Consumo por categoría (por {metrica})")

    # ------------------------------------------------------- evolución mensual
    st.divider()
    st.markdown("**Evolución mes a mes**")
    df_mes = datos["mes"]
    if len(df_mes) > 1:
        st.line_chart(df_mes.set_index("mes")[[columna]], height=260)
        with st.expander("Ver la tabla"):
            st.dataframe(df_mes, width='stretch', hide_index=True)
    else:
        st.info("Se necesita más de un mes con movimientos para ver la evolución.")

    st.caption(
        "Nota: estas cifras salen de lo registrado en este sistema, así que solo cubren "
        "las entregas hechas a través de él. Los movimientos cargados directamente en SMC "
        "no aparecen acá."
    )


def panel_correos_autorizados():
    st.subheader("Correos autorizados para hacer solicitudes")
    st.caption(
        "Solo los correos de esta nómina pueden registrarse y pedir insumos. Validar el dominio "
        "no basta: cualquiera podría inventar un correo del dominio municipal sin ser esa persona. "
        "Esta lista es el control real, y la administra usted."
    )

    st.markdown("**Autorizar un correo**")
    # nonce: al subir, Streamlit crea los tres campos de nuevo con clave
    # distinta (y por lo tanto vacíos), en vez de dejar lo que ya se escribió.
    if "correo_alta_nonce" not in st.session_state:
        st.session_state.correo_alta_nonce = 0
    n = st.session_state.correo_alta_nonce
    if st.session_state.get("correo_alta_ok"):
        st.success("Se ha autorizado un nuevo correo de usuario.")
        st.session_state.correo_alta_ok = False

    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    correo_nuevo = c1.text_input("Correo institucional", key=f"correo_alta_{n}")
    nombre_ref = c2.text_input("Nombre (referencia)", key=f"nombre_alta_{n}")
    area_ref = c3.text_input("Área / Departamento", key=f"area_alta_{n}")
    if st.button("Autorizar correo", type="primary"):
        ok, mensaje = core.autorizar_correo(correo_nuevo, nombre_ref, area_ref)
        if ok:
            st.session_state.correo_alta_ok = True
            st.session_state.correo_alta_nonce += 1
            st.rerun()
        else:
            st.error(mensaje)

    st.divider()
    st.markdown("**Carga masiva de la nómina municipal**")
    st.caption(
        "Suba un archivo con una columna 'correo' (opcionalmente 'nombre' y 'area'). "
        "Es la forma rápida de cargar de una vez todos los correos de la municipalidad."
    )
    archivo = st.file_uploader("Nómina de correos (.xlsx o .csv)", type=["xlsx", "csv"],
                               key="upload_correos")
    if archivo is not None and st.button("Procesar nómina"):
        try:
            resultados = core.importar_correos_desde_excel(archivo)
        except Exception as e:
            st.error(f"No se pudo leer el archivo: {e}")
        else:
            if resultados.empty:
                st.warning("El archivo no traía correos.")
            else:
                st.success(f"{(resultados['resultado'] == 'autorizado').sum()} correo(s) autorizados.")
                st.dataframe(resultados, width='stretch', hide_index=True)

    st.divider()
    st.markdown("**Nómina actual**")
    df = core.listar_correos_autorizados()
    if df.empty:
        st.warning(
            "La nómina está vacía: hoy nadie puede registrarse como solicitante. "
            "Autorice al menos un correo para habilitar el uso."
        )
        return

    filtro = st.text_input("Buscar correo", key="filtro_correos")
    if filtro:
        f = core.normalizar(filtro)
        df = df[df.apply(lambda r: f in core.normalizar(" ".join(str(v) for v in r.values)), axis=1)]

    st.dataframe(df, width='stretch', hide_index=True)

    st.markdown("**Quitar acceso**")
    st.caption(
        "Bloquear deja el correo en la nómina, marcado como bloqueado (queda registro de que "
        "existió). Eliminar lo saca por completo de la lista, sin bloquearlo — para reintegrarlo "
        "más adelante hay que autorizarlo de nuevo desde cero, con sus datos."
    )
    activos = core.listar_correos_autorizados()
    activos = activos[activos["estado"] == "autorizado"]["correo"].tolist()
    if activos:
        a_gestionar = st.selectbox("Correo a bloquear o eliminar", [""] + activos, key="sel_bloqueo")
        if a_gestionar:
            c_bloquear, c_eliminar = st.columns(2)
            with c_bloquear:
                if st.button("Bloquear este correo", width='stretch'):
                    core.bloquear_correo(a_gestionar)
                    st.success(f"{a_gestionar} quedó bloqueado — ya no puede hacer solicitudes.")
                    st.rerun()
            with c_eliminar:
                if st.button("Eliminar de la nómina (sin bloquear)", width='stretch'):
                    core.eliminar_correo_autorizado(a_gestionar)
                    st.success(f"{a_gestionar} se eliminó de la nómina. Para reintegrarlo, autorícelo de nuevo.")
                    st.rerun()


def panel_sync_smc():
    st.subheader("Sincronización con SMC")
    st.caption(
        "Hoy no está confirmado si SMC tiene una vía de integración (import de archivo, ODBC, API). "
        "Mientras se confirma, este panel deja un archivo CSV con los movimientos cerrados pendientes, "
        "listo para importarlo a SMC si esa opción existe, o como respaldo de auditoría si no."
    )
    pendientes = core.obtener_pendientes_sync()
    st.metric("Folios cerrados pendientes de sincronizar", pendientes["folio"].nunique() if not pendientes.empty else 0)

    if st.button("Generar archivo de sincronización ahora"):
        os.makedirs("sync_exports", exist_ok=True)
        ruta, n = core.generar_archivo_sync_smc("sync_exports")
        if ruta is None:
            st.info("No había movimientos pendientes.")
        else:
            st.success(f"Archivo generado: {ruta} ({n} folios).")
            st.rerun()

    st.subheader("Historial de corridas")
    st.dataframe(core.historial_sincronizacion(), width='stretch', hide_index=True)
    st.caption(
        "Para producción: programar esto cada 10 min con el Programador de tareas de Windows o cron "
        "(ver sincronizar_smc.py). Es un job aparte de esta interfaz."
    )
