# -*- coding: utf-8 -*-
"""
formato_impresion.py
Genera los formularios físicos de la Bodega Municipal en PDF:

  1. SOLICITUD DE MATERIALES        — la llena el solicitante y la hace firmar.
  2. COMPROBANTE MOVIMIENTOS EN BODEGA — lo emite el encargado al entregar,
     con la cantidad realmente entregada.

Correcciones del día 5:
  - El título ya no se encima con el recuadro del N°: el número usa fuente
    más chica y el título va en su propia línea, no compartiendo altura.
  - El encabezado de la columna de cantidad ya no se sale de su celda
    (decía "CANT. ENTREGADA", 77 pt de ancho en una columna de 62 pt).
  - USUARIO e INFORMACIÓN ADICIONAL van en el bloque superior izquierdo.
  - Los datos van en mayúsculas.
  - El texto de INFORMACIÓN ADICIONAL viene ya redactado desde la interfaz
    (el encargado lo edita antes de descargar); no se imprime una línea en
    blanco para rellenar a mano.

Los textos fijos están todos como constantes acá abajo para poder ajustarlos
sin tocar el resto del código.
"""

from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# --------------------------------------------------------------- etiquetas
ENCABEZADO_LINEAS = [
    "MUNICIPALIDAD DE TRAIGUÉN",
    "BODEGA MUNICIPAL",
    "Dirección de Administración y Finanzas",
]
TITULO_SOLICITUD = "ENTREGA DE MATERIALES"
ETIQUETA_SOLICITUD_NUM = "SOLICITUD N°"
COL_COMENTARIOS = "COMENTARIOS"
COL_CHEQUEO = "CHEQUEO"
ETIQUETA_PERSONA_RETIRA = "PERSONA QUE RETIRA:"
ETIQUETA_NOMBRE_DIRECTOR = "NOMBRE DIRECTOR:"
ETIQUETA_FIRMA = "FIRMA"
TITULO_COMPROBANTE = "COMPROBANTE MOVIMIENTOS DE BODEGA"

ETIQUETA_NUMERO = "N°"
ETIQUETA_SOLICITANTE = "SOLICITANTE"
ETIQUETA_DEPARTAMENTO = "DEPARTAMENTO"
ETIQUETA_OFICINA = "OFICINA"
ETIQUETA_FECHA = "FECHA"
ETIQUETA_USUARIO = "USUARIO"
ETIQUETA_SUPERVISOR = "SUPERVISOR / JEFATURA"
ETIQUETA_INFO_ADICIONAL = "INFORMACIÓN ADICIONAL"

COL_CANTIDAD = "CANTIDAD"
COL_CANTIDAD_ENTREGADA = "ENTREGADO"
COL_UNIDAD = "UNIDAD"
COL_DETALLE = "DETALLE"          # tabla de la solicitud
COL_DESCRIPCION = "DESCRIPCION"  # tabla del comprobante
COL_LOTE = "LOTE/FECHA"
COL_PROX_PEDIDO = "PROX. PEDIDO"
ETIQUETA_MES = "MES:"
ETIQUETA_TRANSACCION = "N° TRANSACCION"
ETIQUETA_MEMO = "MEMO"
ETIQUETA_DEPTO_ORIGEN = "DEPTO. ORIGEN"
ETIQUETA_TIPO_MOV = "TIPO MOVIMIENTO"
ETIQUETA_DESTINO = "DESTINO"
ETIQUETA_CCOSTO = "C. COSTO"
ETIQUETA_DEPENDENCIA = "DEPENDENCIA"
FIRMA_ENCARGADO_BODEGA = "Encargado(a) de bodega"
MEMO_POR_DEFECTO = "0"
TIPO_MOVIMIENTO_POR_DEFECTO = "SALIDA"
DESTINO_POR_DEFECTO = "CONSUMO"
COL_CODIGO = "COD. ART."

FIRMA_SOLICITANTE = "FIRMA SOLICITANTE"
FIRMA_JEFATURA = "V°B° JEFATURA / SUPERVISOR"
FIRMA_ENTREGA = "FIRMA ENCARGADO BODEGA (ENTREGA)"
FIRMA_RETIRA = "FIRMA QUIEN RETIRA (RECIBE CONFORME)"

# ----------------------------------------------------------------- medidas
ANCHO, ALTO = letter
MARGEN = 18 * mm
FILAS_EXTRA = 2          # filas en blanco de cortesía
ALTO_FILA = 15
ANCHO_CAJA_NUM = 34 * mm
ALTO_CAJA_NUM = 11 * mm


def _mayus(valor) -> str:
    return str(valor or "").strip().upper()


def _fecha_legible(fecha_texto):
    """'2026-07-20 14:59' -> '20/07/2026'. Si viene raro, se devuelve tal cual."""
    try:
        return datetime.strptime(str(fecha_texto)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(fecha_texto or "")


# Desde este correlativo, el folio impreso ya NO es el correlativo interno del
# sistema, sino el folio REAL de SMC que el encargado asigna a mano (SMC comparte
# el contador con el sistema de vales de gas y salta números, así que el
# correlativo automático no coincide con el papel). En la solicitud sale en
# blanco (se llena a mano); en el comprobante lo escribe el encargado antes de
# imprimir. Las anteriores (< este número) siguen mostrando su correlativo.
FOLIO_MANUAL_DESDE = 3035


def numero_folio_impreso(cabecera):
    """Número que va en el recuadro N° del documento: el folio_real (SMC) si ya
    se asignó; si no, el correlativo para las históricas (< FOLIO_MANUAL_DESDE),
    o vacío para las nuevas (se rellena a mano)."""
    fr = str(cabecera.get("folio_real") or "").strip()
    if fr:
        return fr
    corr = cabecera.get("correlativo")
    try:
        if corr is not None and int(corr) < FOLIO_MANUAL_DESDE:
            return str(corr)
    except (TypeError, ValueError):
        pass
    return ""


def _encabezado(c, titulo, correlativo):
    """Bloque institucional a la izquierda, recuadro del N° a la derecha,
    y el título en su propia franja (así no se encima con nada)."""
    y = ALTO - MARGEN

    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEN, y, ENCABEZADO_LINEAS[0])
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGEN, y - 11, ENCABEZADO_LINEAS[1])
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGEN, y - 21, ENCABEZADO_LINEAS[2])

    caja_x = ANCHO - MARGEN - ANCHO_CAJA_NUM
    caja_y = y - ALTO_CAJA_NUM + 6
    c.setLineWidth(1)
    c.rect(caja_x, caja_y, ANCHO_CAJA_NUM, ALTO_CAJA_NUM)
    c.setFont("Helvetica", 7)
    c.drawString(caja_x + 4, caja_y + ALTO_CAJA_NUM - 8, ETIQUETA_NUMERO)
    c.setFont("Helvetica-Bold", 12)   # antes 18: ocupaba demasiado
    c.drawRightString(caja_x + ANCHO_CAJA_NUM - 5, caja_y + 3, str(correlativo or "—"))

    y_titulo = y - 40
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(ANCHO / 2, y_titulo, titulo)
    c.setLineWidth(1)
    c.line(MARGEN, y_titulo - 7, ANCHO - MARGEN, y_titulo - 7)

    return y_titulo - 22


def _campo(c, x, y, etiqueta, valor, ancho, tam_valor=8.5):
    """Etiqueta + valor sobre una línea."""
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x, y, f"{etiqueta}:")
    desplazamiento = c.stringWidth(f"{etiqueta}:", "Helvetica-Bold", 7.5) + 4
    c.setFont("Helvetica", tam_valor)
    c.drawString(x + desplazamiento, y, _mayus(valor))
    c.setLineWidth(0.4)
    c.line(x + desplazamiento, y - 2.5, x + ancho, y - 2.5)


def _parrafo(c, x, y, texto, ancho_max, tam=8, interlineado=11):
    """Escribe un texto ajustándolo al ancho disponible, cortando por palabras."""
    palabras = _mayus(texto).split()
    c.setFont("Helvetica", tam)
    linea = ""
    for palabra in palabras:
        prueba = (linea + " " + palabra).strip()
        if c.stringWidth(prueba, "Helvetica", tam) <= ancho_max:
            linea = prueba
        else:
            c.drawString(x, y, linea)
            y -= interlineado
            linea = palabra
    if linea:
        c.drawString(x, y, linea)
        y -= interlineado
    return y


def _datos_cabecera(c, y, cabecera, con_usuario=False, con_supervisor=False,
                    con_info_adicional=False):
    util = ANCHO - 2 * MARGEN

    _campo(c, MARGEN, y, ETIQUETA_SOLICITANTE, cabecera.get("solicitante"), util * 0.60)
    _campo(c, MARGEN + util * 0.64, y, ETIQUETA_FECHA,
           _fecha_legible(cabecera.get("fecha_solicitud")), util * 0.36)
    y -= 17

    _campo(c, MARGEN, y, ETIQUETA_DEPARTAMENTO, cabecera.get("area_departamento"), util * 0.60)
    _campo(c, MARGEN + util * 0.64, y, ETIQUETA_OFICINA, cabecera.get("oficina"), util * 0.36)
    y -= 17

    if con_supervisor:
        _campo(c, MARGEN, y, ETIQUETA_SUPERVISOR, cabecera.get("supervisor"), util)
        y -= 17

    if con_usuario:
        # Quién realizó el movimiento, arriba a la izquierda.
        _campo(c, MARGEN, y, ETIQUETA_USUARIO, cabecera.get("usuario_operacion"), util * 0.60)
        y -= 17

    if con_info_adicional:
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(MARGEN, y, f"{ETIQUETA_INFO_ADICIONAL}:")
        y -= 12
        y = _parrafo(c, MARGEN, y, cabecera.get("info_adicional"), util)
        y -= 2

    return y - 6


def _tabla(c, y, items, columna_cantidad, titulo_cantidad, con_codigo=False):
    """
    Tabla de insumos. Los anchos se calculan a partir del texto de los
    encabezados, para que ninguno se salga de su celda.
    """
    util = ANCHO - 2 * MARGEN
    ancho_cant = max(30 * mm, c.stringWidth(titulo_cantidad, "Helvetica-Bold", 7.5) + 14)
    ancho_unidad = 20 * mm
    ancho_codigo = 24 * mm if con_codigo else 0
    ancho_detalle = util - ancho_cant - ancho_unidad - ancho_codigo

    x_cant = MARGEN
    x_unidad = x_cant + ancho_cant
    x_codigo = x_unidad + ancho_unidad
    x_detalle = x_codigo + ancho_codigo

    separadores = [x_unidad, x_detalle] + ([x_codigo] if con_codigo else [])
    n_filas = len(items) + FILAS_EXTRA

    # cabecera
    c.setLineWidth(1)
    c.rect(x_cant, y - ALTO_FILA, util, ALTO_FILA)
    for x in separadores:
        c.line(x, y - ALTO_FILA, x, y)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(x_cant + ancho_cant / 2, y - 10, titulo_cantidad)
    c.drawCentredString(x_unidad + ancho_unidad / 2, y - 10, COL_UNIDAD)
    if con_codigo:
        c.drawCentredString(x_codigo + ancho_codigo / 2, y - 10, COL_CODIGO)
    c.drawCentredString(x_detalle + ancho_detalle / 2, y - 10, COL_DESCRIPCION)
    y -= ALTO_FILA

    c.setLineWidth(0.5)
    for i in range(n_filas):
        fila_y = y - (i + 1) * ALTO_FILA
        c.rect(x_cant, fila_y, util, ALTO_FILA)
        for x in separadores:
            c.line(x, fila_y, x, fila_y + ALTO_FILA)

        if i < len(items):
            item = items[i]
            cantidad = item.get(columna_cantidad)
            if cantidad is None:
                cantidad = item.get("cantidad_solicitada")
            c.setFont("Helvetica", 8.5)
            c.drawCentredString(x_cant + ancho_cant / 2, fila_y + 4.5, str(cantidad))
            c.drawCentredString(x_unidad + ancho_unidad / 2, fila_y + 4.5,
                                _mayus(item.get("unidad")))
            if con_codigo:
                c.drawCentredString(x_codigo + ancho_codigo / 2, fila_y + 4.5,
                                    str(item.get("codigo") or ""))
            detalle = _mayus(item.get("producto"))
            if c.stringWidth(detalle, "Helvetica", 8.5) > ancho_detalle - 8:
                while (c.stringWidth(detalle + "...", "Helvetica", 8.5) > ancho_detalle - 8
                       and len(detalle) > 4):
                    detalle = detalle[:-1]
                detalle += "..."
            c.drawString(x_detalle + 4, fila_y + 4.5, detalle)

    return y - n_filas * ALTO_FILA - 16


def _firmas(c, y, etiqueta_izq, etiqueta_der):
    util = ANCHO - 2 * MARGEN
    ancho_bloque = util * 0.42
    y_linea = max(y - 34, MARGEN + 34)
    for x_inicio, etiqueta in (
        (MARGEN, etiqueta_izq),
        (ANCHO - MARGEN - ancho_bloque, etiqueta_der),
    ):
        c.setLineWidth(0.8)
        c.line(x_inicio, y_linea, x_inicio + ancho_bloque, y_linea)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x_inicio + ancho_bloque / 2, y_linea - 10, etiqueta)
    return y_linea - 24


def _pie(c, cabecera):
    c.setFont("Helvetica", 6.5)
    c.setFillGray(0.45)
    c.drawString(MARGEN, MARGEN - 6,
                 f"{cabecera.get('folio','')} · generado el "
                 f"{datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.setFillGray(0)


def generar_solicitud_pdf(ruta_salida, cabecera, items):
    """
    Formulario ENTREGA DE MATERIALES, replicando el formato en papel
    (diagnóstico 5.2). La tabla lleva cuatro columnas:
      - CANTIDAD y DETALLE salen prellenados desde el sistema.
      - COMENTARIOS queda en blanco: lo usa quien pide para anotar dudas
        (ej. si no está seguro de haber reconocido bien el producto).
      - CHEQUEO queda en blanco: lo usa el funcionario de bodega para marcar
        y anotar las cantidades realmente entregadas antes de registrarlas.
    """
    c = canvas.Canvas(str(ruta_salida), pagesize=letter)
    c.setTitle(f"Entrega de materiales N° {cabecera.get('correlativo','')}")
    util = ANCHO - 2 * MARGEN

    y = ALTO - MARGEN - 10
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(ANCHO / 2, y, TITULO_SOLICITUD)

    # N° de solicitud, arriba a la derecha
    y -= 26
    c.setFont("Helvetica-Bold", 9)
    etiqueta_num = f"{ETIQUETA_SOLICITUD_NUM} "
    ancho_etiqueta = c.stringWidth(etiqueta_num, "Helvetica-Bold", 9)
    x_num = ANCHO - MARGEN - 70
    c.drawString(x_num - ancho_etiqueta, y, etiqueta_num)
    c.setFont("Helvetica-Bold", 11)
    # Para las solicitudes nuevas queda en blanco: el folio real (SMC) se escribe
    # a mano sobre esta línea (ver numero_folio_impreso / FOLIO_MANUAL_DESDE).
    c.drawString(x_num + 4, y, numero_folio_impreso(cabecera))
    c.setLineWidth(0.6)
    c.line(x_num, y - 3, ANCHO - MARGEN, y - 3)

    # Campos: fecha / departamento / oficina
    y -= 24
    _campo(c, MARGEN, y, ETIQUETA_FECHA, _fecha_legible(cabecera.get("fecha_solicitud")),
           util * 0.55)
    y -= 22
    _campo(c, MARGEN, y, ETIQUETA_DEPARTAMENTO, cabecera.get("area_departamento"), util * 0.48)
    _campo(c, MARGEN + util * 0.54, y, ETIQUETA_OFICINA, cabecera.get("oficina"), util * 0.46)

    # ---- tabla normal (con cuadrícula), cuatro columnas
    y -= 26
    anchos = [26 * mm, 74 * mm, 44 * mm, 28 * mm]
    anchos[1] = util - (anchos[0] + anchos[2] + anchos[3])
    titulos = [COL_CANTIDAD, COL_DETALLE, COL_COMENTARIOS, COL_CHEQUEO]
    xs, x = [], MARGEN
    for ancho in anchos:
        xs.append(x)
        x += ancho

    alto_fila = 17
    n_filas = len(items) + FILAS_EXTRA

    c.setLineWidth(1)
    c.rect(MARGEN, y - alto_fila, util, alto_fila)
    for x_col in xs[1:]:
        c.line(x_col, y - alto_fila, x_col, y)
    c.setFont("Helvetica-Bold", 8)
    for indice, titulo in enumerate(titulos):
        c.drawCentredString(xs[indice] + anchos[indice] / 2, y - 11, titulo)
    y -= alto_fila

    c.setLineWidth(0.6)
    for i in range(n_filas):
        fila_y = y - (i + 1) * alto_fila
        c.rect(MARGEN, fila_y, util, alto_fila)
        for x_col in xs[1:]:
            c.line(x_col, fila_y, x_col, fila_y + alto_fila)

        if i < len(items):
            item = items[i]
            c.setFont("Helvetica", 9)
            c.drawCentredString(xs[0] + anchos[0] / 2, fila_y + 5,
                                str(item.get("cantidad_solicitada")))
            detalle = _mayus(item.get("producto"))
            if c.stringWidth(detalle, "Helvetica", 9) > anchos[1] - 8:
                while (c.stringWidth(detalle + "...", "Helvetica", 9) > anchos[1] - 8
                       and len(detalle) > 4):
                    detalle = detalle[:-1]
                detalle += "..."
            c.drawString(xs[1] + 4, fila_y + 5, detalle)
            # COMENTARIOS y CHEQUEO quedan vacías a propósito: se llenan a mano.

    y = y - n_filas * alto_fila - 34

    # ---- firmas: nombre largo a la izquierda, firma a la derecha
    for etiqueta, nombre in (
        (ETIQUETA_PERSONA_RETIRA, cabecera.get("solicitante")),
        (ETIQUETA_NOMBRE_DIRECTOR, cabecera.get("supervisor")),
    ):
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGEN, y, etiqueta)
        x_nombre = MARGEN + 105
        ancho_nombre = util * 0.44          # espacio holgado para dos apellidos
        c.setFont("Helvetica", 9)
        c.drawString(x_nombre + 4, y, _mayus(nombre))
        c.setLineWidth(0.6)
        c.line(x_nombre, y - 3, x_nombre + ancho_nombre, y - 3)

        x_firma = x_nombre + ancho_nombre + 16
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x_firma, y, ETIQUETA_FIRMA)
        c.line(x_firma + 34, y - 3, ANCHO - MARGEN, y - 3)
        y -= 34

    _pie(c, cabecera)
    c.showPage()
    c.save()
    return str(ruta_salida)


def _meses_encabezado(fecha_texto):
    """
    Los dos rótulos que van sobre CANTIDAD y PROX. PEDIDO. En el comprobante
    original de abril decían "abr./may." y "jun./jul.", o sea: el bimestre en
    curso y el siguiente. Se calculan desde la fecha del documento.
    """
    nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        fecha = datetime.strptime(str(fecha_texto)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        fecha = datetime.now()
    m = fecha.month - 1
    def par(inicio):
        return f"{nombres[inicio % 12]}/{nombres[(inicio + 1) % 12]}"
    return par(m), par(m + 2)


def _cabecera_comprobante(c, cabecera, y_inicio=None):
    """
    Encabezado del comprobante replicando el formato en papel:
    institución arriba a la izquierda, fecha/hora y paginación a la derecha,
    título al centro, USUARIO a la derecha, bloque de datos del movimiento a
    la izquierda e INFORMACIÓN ADICIONAL a la derecha.
    """
    util = ANCHO - 2 * MARGEN
    y = ALTO - MARGEN if y_inicio is None else y_inicio

    c.setFont("Helvetica", 9)
    c.drawString(MARGEN, y, ENCABEZADO_LINEAS[0])
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGEN, y - 11, "BODEGA MUNICIPAL")

    generado = datetime.now()
    c.setFont("Helvetica", 7.5)
    c.drawRightString(ANCHO - MARGEN, y,
                      f"FECHA: {_fecha_legible(cabecera.get('fecha_solicitud'))}  "
                      f"{generado.strftime('%H:%M:%S')}")
    c.drawRightString(ANCHO - MARGEN, y - 11, "Página 1 de 1")

    y -= 34
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(ANCHO / 2, y, TITULO_COMPROBANTE)

    y -= 18
    # USUARIO va sobre la columna derecha, como en el formato original.
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGEN + util * 0.55, y, f"{ETIQUETA_USUARIO}: ")
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGEN + util * 0.55 + 42, y, _mayus(cabecera.get("usuario_operacion")))

    y -= 16
    y_bloque = y

    # ---- columna izquierda: datos del movimiento
    tipo_mov = cabecera.get("tipo_movimiento") or TIPO_MOVIMIENTO_POR_DEFECTO
    destino = cabecera.get("destino") or DESTINO_POR_DEFECTO
    izq = [
        (ETIQUETA_TRANSACCION, numero_folio_impreso(cabecera)),
        (ETIQUETA_DEPTO_ORIGEN, cabecera.get("depto_origen") or cabecera.get("area_departamento")),
        (ETIQUETA_TIPO_MOV, f"*** {tipo_mov} ***"),
        (ETIQUETA_DESTINO, f"*** {destino} ***"),
        (ETIQUETA_CCOSTO, ""),
        (ETIQUETA_DEPENDENCIA, cabecera.get("oficina")),
    ]
    yi = y_bloque
    x_valor = MARGEN + 88
    # el valor no puede invadir la columna derecha (INFORMACIÓN ADICIONAL)
    ancho_valor = (MARGEN + util * 0.55) - x_valor - 8
    for etiqueta, valor in izq:
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN, yi, f"{etiqueta}:")
        texto = _mayus(valor)
        # se achica la fuente lo justo para que quepa; si aun así no entra,
        # se recorta. Pasa con nombres largos como "DIRECCIÓN DE
        # ADMINISTRACIÓN Y FINANZAS".
        tam = 8.5
        while tam > 6 and c.stringWidth(texto, "Helvetica", tam) > ancho_valor:
            tam -= 0.5
        if c.stringWidth(texto, "Helvetica", tam) > ancho_valor:
            while (c.stringWidth(texto + "...", "Helvetica", tam) > ancho_valor
                   and len(texto) > 4):
                texto = texto[:-1]
            texto += "..."
        c.setFont("Helvetica", tam)
        c.drawString(x_valor, yi, texto)
        yi -= 13

    # MEMO va en la misma línea que N° TRANSACCION, como en el original
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGEN + util * 0.30, y_bloque, f"{ETIQUETA_MEMO}:")
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGEN + util * 0.30 + 34, y_bloque,
                 str(cabecera.get("memo") or MEMO_POR_DEFECTO))

    # ---- columna derecha: información adicional
    x_der = MARGEN + util * 0.55
    ancho_der = util * 0.45
    c.setFont("Helvetica", 7.5)
    c.drawString(x_der, y_bloque, ETIQUETA_INFO_ADICIONAL)
    yd = _parrafo(c, x_der, y_bloque - 12, cabecera.get("info_adicional"), ancho_der,
                  tam=8, interlineado=10)

    return min(yi, yd) - 12


def _tabla_comprobante(c, y, items, fecha_texto):
    """
    Tabla del comprobante con las seis columnas del formato real y el
    cuadro de meses (2x1) que va sobre CANTIDAD y PROX. PEDIDO.
    """
    util = ANCHO - 2 * MARGEN
    anchos = {
        "codigo": 22 * mm,
        "descripcion": util - (22 * mm + 22 * mm + 18 * mm + 26 * mm + 28 * mm),
        "lote": 22 * mm,
        "unidad": 18 * mm,
        "cantidad": 26 * mm,
        "prox": 28 * mm,
    }
    orden = ["codigo", "descripcion", "lote", "unidad", "cantidad", "prox"]
    xs = {}
    x = MARGEN
    for clave in orden:
        xs[clave] = x
        x += anchos[clave]

    # ---- cuadro de MES sobre las dos últimas columnas
    mes_actual, mes_prox = _meses_encabezado(fecha_texto)
    alto_mes = 13
    x_mes = xs["cantidad"]
    ancho_mes = anchos["cantidad"] + anchos["prox"]

    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(x_mes - 6, y - 9, ETIQUETA_MES)
    c.setLineWidth(1)
    c.rect(x_mes, y - alto_mes, ancho_mes, alto_mes)
    c.line(xs["prox"], y - alto_mes, xs["prox"], y)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(xs["cantidad"] + anchos["cantidad"] / 2, y - 9, mes_actual)
    c.drawCentredString(xs["prox"] + anchos["prox"] / 2, y - 9, mes_prox)
    y -= alto_mes

    # ---- fila de encabezados: negrita, solo con línea inferior
    titulos = {
        "codigo": COL_CODIGO, "descripcion": COL_DESCRIPCION, "lote": COL_LOTE,
        "unidad": COL_UNIDAD, "cantidad": COL_CANTIDAD, "prox": COL_PROX_PEDIDO,
    }
    c.setFont("Helvetica-Bold", 7)
    for clave in orden:
        c.drawCentredString(xs[clave] + anchos[clave] / 2, y - 10, titulos[clave])
    c.setLineWidth(1)
    c.setDash()
    c.line(MARGEN, y - ALTO_FILA, MARGEN + util, y - ALTO_FILA)
    y -= ALTO_FILA

    # ---- filas de productos: sin cuadrícula, solo línea inferior punteada
    n_filas = len(items) + FILAS_EXTRA
    for i in range(n_filas):
        fila_y = y - (i + 1) * ALTO_FILA

        if i < len(items):
            item = items[i]
            cantidad = item.get("cantidad_entregada")
            if cantidad is None:
                cantidad = item.get("cantidad_solicitada")
            c.setFont("Helvetica", 8)
            c.drawCentredString(xs["codigo"] + anchos["codigo"] / 2, fila_y + 4.5,
                                str(item.get("codigo") or ""))
            c.drawCentredString(xs["unidad"] + anchos["unidad"] / 2, fila_y + 4.5,
                                _mayus(item.get("unidad")))
            c.drawCentredString(xs["cantidad"] + anchos["cantidad"] / 2, fila_y + 4.5,
                                f"{cantidad},00")
            detalle = _mayus(item.get("producto"))
            ancho_desc = anchos["descripcion"]
            if c.stringWidth(detalle, "Helvetica", 8) > ancho_desc - 8:
                while (c.stringWidth(detalle + "...", "Helvetica", 8) > ancho_desc - 8
                       and len(detalle) > 4):
                    detalle = detalle[:-1]
                detalle += "..."
            c.drawString(xs["descripcion"] + 4, fila_y + 4.5, detalle)

        # línea punteada bajo cada fila, hasta que se acaban los productos
        c.setLineWidth(0.5)
        c.setDash(1, 2)
        c.line(MARGEN, fila_y, MARGEN + util, fila_y)
    c.setDash()

    return y - n_filas * ALTO_FILA - 30


def alto_estimado_comprobante(items) -> float:
    """
    Alto aproximado que ocupa un comprobante. Sirve para decidir si dos
    caben en una misma hoja antes de intentar juntarlos.
    """
    fijo = 34 + 18 + 16 + (6 * 13) + 13 + ALTO_FILA + 40 + 20
    return fijo + (len(items) + FILAS_EXTRA) * ALTO_FILA


def cabe_en_media_hoja(items) -> bool:
    return alto_estimado_comprobante(items) <= (ALTO / 2) - 24


def _bloque_comprobante(c, cabecera, items, y_inicio, piso):
    """Dibuja un comprobante completo entre y_inicio y piso."""
    y = _cabecera_comprobante(c, cabecera, y_inicio=y_inicio)
    y = _tabla_comprobante(c, y, items, cabecera.get("fecha_solicitud"))

    ancho_linea = 62 * mm
    x_linea = (ANCHO - ancho_linea) / 2
    y_linea = max(y - 24, piso + 26)
    c.setLineWidth(0.8)
    c.setDash()
    c.line(x_linea, y_linea, x_linea + ancho_linea, y_linea)
    c.setFont("Helvetica", 8)
    c.drawCentredString(ANCHO / 2, y_linea - 11, FIRMA_ENCARGADO_BODEGA)
    return y_linea - 11


def generar_comprobantes_pareados_pdf(ruta_salida, comprobantes):
    """
    Junta comprobantes de a dos por hoja, separados por una línea de corte
    punteada, para no gastar una hoja entera en pedidos chicos.

    comprobantes: lista de (cabecera, items). Los que no caben en media hoja
    se emiten solos en su propia página, para no cortar la tabla por la mitad.
    """
    c = canvas.Canvas(str(ruta_salida), pagesize=letter)
    c.setTitle("Comprobantes de bodega")
    mitad = ALTO / 2

    # se separan los que caben en media hoja de los que no
    chicos = [cp for cp in comprobantes if cabe_en_media_hoja(cp[1])]
    grandes = [cp for cp in comprobantes if not cabe_en_media_hoja(cp[1])]

    for i in range(0, len(chicos), 2):
        pareja = chicos[i:i + 2]

        # arriba
        _bloque_comprobante(c, pareja[0][0], pareja[0][1],
                            y_inicio=ALTO - MARGEN, piso=mitad)

        # abajo (si hay segundo)
        if len(pareja) == 2:
            _bloque_comprobante(c, pareja[1][0], pareja[1][1],
                                y_inicio=mitad - 20, piso=MARGEN)

        # línea de corte al medio
        c.saveState()
        c.setDash(3, 3)
        c.setLineWidth(0.6)
        c.setStrokeGray(0.45)
        c.line(MARGEN / 2, mitad, ANCHO - MARGEN / 2, mitad)
        c.setFont("Helvetica", 6)
        c.setFillGray(0.45)
        c.drawString(MARGEN / 2, mitad + 3, "- - - cortar por aquí - - -")
        c.restoreState()
        c.showPage()

    for cabecera, items in grandes:
        _bloque_comprobante(c, cabecera, items, y_inicio=ALTO - MARGEN, piso=MARGEN)
        _pie(c, cabecera)
        c.showPage()

    c.save()
    return str(ruta_salida)


def generar_comprobante_pdf(ruta_salida, cabecera, items):
    """
    Comprobante de movimientos de bodega, replicando el formato en papel
    transcrito en el diagnóstico 5.1.
    """
    # Lo que se redujo a cero no se entregó, así que no corresponde que
    # aparezca en el comprobante de retiro: quien firma estaría respaldando
    # la recepción de algo que nunca salió de bodega.
    items = [it for it in items
             if (it.get("cantidad_entregada")
                 if it.get("cantidad_entregada") is not None
                 else it.get("cantidad_solicitada")) not in (0, None)]

    c = canvas.Canvas(str(ruta_salida), pagesize=letter)
    c.setTitle(f"Comprobante movimientos de bodega N° {cabecera.get('correlativo','')}")

    y = _cabecera_comprobante(c, cabecera)
    y = _tabla_comprobante(c, y, items, cabecera.get("fecha_solicitud"))

    # firma única del encargado, al centro
    ancho_linea = 62 * mm
    x_linea = (ANCHO - ancho_linea) / 2
    y_linea = max(y - 24, MARGEN + 30)
    c.setLineWidth(0.8)
    c.line(x_linea, y_linea, x_linea + ancho_linea, y_linea)
    c.setFont("Helvetica", 8)
    c.drawCentredString(ANCHO / 2, y_linea - 11, FIRMA_ENCARGADO_BODEGA)

    _pie(c, cabecera)
    c.showPage()
    c.save()
    return str(ruta_salida)
