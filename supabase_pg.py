# -*- coding: utf-8 -*-
"""
supabase_pg.py — cliente para la base compartida en Supabase (Postgres),
sobre psycopg2.

Por qué psycopg2 y no una API HTTP (como turso_http.py con Turso): Postgres
no ofrece una API pública sobre HTTP, así que acá sí hace falta un driver
nativo. psycopg2-binary trae wheel precompilado para Windows/Python 3.14
(desde la versión 2.9.12), así que no exige instalar Rust ni Visual Studio
Build Tools — se mantiene la misma restricción que llevó a escribir
turso_http.py a mano en su momento.

Imita la parte de la interfaz de sqlite3.Connection que core.py realmente
usa (execute/commit/close, encadenado con fetchone/fetchall, compatible con
pandas.read_sql, cursor()), igual que hacía turso_http.py, para que core.py
no tenga que tratar esto como un caso especial.

Pool de conexiones: a diferencia de una request HTTP, abrir una conexión
Postgres nueva implica un handshake TCP+TLS+autenticación completo. Si cada
get_connection() de core.py abriera y cerrara una conexión real por llamada
(hay ~100 en el archivo), ese costo se pagaría una y otra vez en cada
corrida — el mismo problema que documenta turso_http.py sobre por qué su
sesión HTTP es compartida a nivel de módulo. Acá el equivalente es un pool
de conexiones a nivel de módulo: close() devuelve la conexión al pool en vez
de cerrar el socket.

Autocommit: cada execute() se aplica de inmediato (igual que turso_http.py),
para no depender de que cada función de core.py llame a commit() en el
momento justo, y para que un ALTER TABLE fallido (columna que ya existe) no
deje la conexión con una transacción abortada que bloquee las sentencias
siguientes.

Placeholders: el resto del código usa '?' (estilo sqlite3); psycopg2 espera
'%s'. Se traduce automáticamente acá, respetando literales de texto entre
comillas simples y comentarios de línea, para no tener que tocar cada
sentencia SQL de core.py.
"""

import threading

import psycopg2
import psycopg2.pool

TIMEOUT_SEGUNDOS = 20

_pool_lock = threading.Lock()
_pool = None
_pool_dsn = None


class SupabaseError(Exception):
    """Error devuelto por la base (SQL inválido, etc.) o de red."""


def _obtener_pool(dsn):
    global _pool, _pool_dsn
    with _pool_lock:
        if _pool is None or _pool_dsn != dsn:
            if _pool is not None:
                _pool.closeall()
            _pool = psycopg2.pool.ThreadedConnectionPool(
                1, 10, dsn, connect_timeout=TIMEOUT_SEGUNDOS,
            )
            _pool_dsn = dsn
        return _pool


def _partir_sentencias(script_sql):
    """
    Separa un script SQL en sentencias por ';', pero ignorando los ';' que
    aparecen dentro de un comentario de línea ('-- hasta el fin de línea') o
    de un literal de texto entre comillas simples (misma lógica que
    turso_http.py, reproducida acá porque ese archivo ya no se usa).
    """
    sentencias = []
    actual = []
    en_comentario = False
    en_string = False
    i = 0
    n = len(script_sql)
    while i < n:
        c = script_sql[i]
        if en_comentario:
            actual.append(c)
            if c == "\n":
                en_comentario = False
            i += 1
            continue
        if en_string:
            actual.append(c)
            if c == "'":
                en_string = False
            i += 1
            continue
        if c == "-" and script_sql[i:i + 2] == "--":
            en_comentario = True
            actual.append(c)
            i += 1
            continue
        if c == "'":
            en_string = True
            actual.append(c)
            i += 1
            continue
        if c == ";":
            sentencias.append("".join(actual))
            actual = []
            i += 1
            continue
        actual.append(c)
        i += 1
    if actual:
        sentencias.append("".join(actual))
    return sentencias


def _traducir_placeholders(sql):
    """
    Convierte los '?' de estilo sqlite3 a '%s' de estilo psycopg2, ignorando
    los que aparecen dentro de un comentario de línea o de un literal de
    texto entre comillas simples (el SQL de core.py no usa '?' como dato,
    solo como placeholder, pero se camina el string igual por prolijidad).
    """
    resultado = []
    en_comentario = False
    en_string = False
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        if en_comentario:
            resultado.append(c)
            if c == "\n":
                en_comentario = False
            i += 1
            continue
        if en_string:
            resultado.append(c)
            if c == "'":
                en_string = False
            i += 1
            continue
        if c == "-" and sql[i:i + 2] == "--":
            en_comentario = True
            resultado.append(c)
            i += 1
            continue
        if c == "'":
            en_string = True
            resultado.append(c)
            i += 1
            continue
        if c == "?":
            resultado.append("%s")
            i += 1
            continue
        resultado.append(c)
        i += 1
    return "".join(resultado)


class SupabaseCursor:
    """Resultado de un execute(): permite fetchone()/fetchall() encadenados,
    y expone description/rowcount al estilo DBAPI2 para que pandas.read_sql
    pueda leer nombres de columna."""

    def __init__(self, description, filas, rowcount, lastrowid):
        self.description = description
        self._filas = filas
        self._pos = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        if self._pos >= len(self._filas):
            return None
        fila = self._filas[self._pos]
        self._pos += 1
        return fila

    def fetchall(self):
        resto = self._filas[self._pos:]
        self._pos = len(self._filas)
        return resto

    def fetchmany(self, size=1):
        resto = self._filas[self._pos:self._pos + size]
        self._pos += len(resto)
        return resto

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        pass


class _CursorDesdeConexion:
    """Adaptador para que conn.cursor() también sirva (algunas rutas de
    pandas usan cursor() en vez de conn.execute() directo)."""

    def __init__(self, conexion):
        self._conexion = conexion
        self._ultimo = None

    def execute(self, sql, parametros=()):
        self._ultimo = self._conexion.execute(sql, parametros)
        return self

    @property
    def description(self):
        return self._ultimo.description if self._ultimo else None

    @property
    def rowcount(self):
        return self._ultimo.rowcount if self._ultimo else -1

    @property
    def lastrowid(self):
        return self._ultimo.lastrowid if self._ultimo else None

    def fetchone(self):
        return self._ultimo.fetchone() if self._ultimo else None

    def fetchall(self):
        return self._ultimo.fetchall() if self._ultimo else []

    def fetchmany(self, size=1):
        return self._ultimo.fetchmany(size) if self._ultimo else []

    def __iter__(self):
        return iter(self._ultimo) if self._ultimo else iter(())

    def close(self):
        pass


class SupabaseConnection:
    """Conexión a la base compartida en Supabase (tomada de un pool a nivel
    de módulo). Autocommit: cada execute() se aplica de inmediato;
    commit()/rollback() son no-ops. close() devuelve la conexión al pool en
    vez de cerrar el socket."""

    def __init__(self, dsn):
        self._pool = _obtener_pool(dsn)
        try:
            self._conn = self._pool.getconn()
        except psycopg2.Error as e:
            raise SupabaseError(f"No se pudo conectar a Supabase: {e}") from e
        self._conn.autocommit = True

    def execute(self, sql, parametros=()):
        sql_pg = _traducir_placeholders(sql)
        cur = self._conn.cursor()
        try:
            cur.execute(sql_pg, tuple(parametros) if parametros else None)
        except psycopg2.Error as e:
            cur.close()
            raise SupabaseError(f"{e} — SQL: {sql}") from e

        descripcion = cur.description
        filas = cur.fetchall() if descripcion is not None else []
        lastrowid = None
        if descripcion is not None and filas and "returning" in sql_pg.lower():
            lastrowid = filas[0][0]
        resultado = SupabaseCursor(descripcion, filas, cur.rowcount, lastrowid)
        cur.close()
        return resultado

    def executemany(self, sql, secuencia_parametros):
        ultimo = None
        for parametros in secuencia_parametros:
            ultimo = self.execute(sql, parametros)
        return ultimo

    def executescript(self, script_sql):
        """
        Solo se usa para el DDL de init_db. ESQUEMA_SQL (en core.py) es una
        sola cadena compartida con el esquema SQLite real (la usa también
        respaldar_base_local() contra un archivo sqlite3 de verdad), así que
        acá se traduce la única diferencia de dialecto que tiene ese esquema
        —'INTEGER PRIMARY KEY AUTOINCREMENT' no existe en Postgres, el
        equivalente es 'SERIAL PRIMARY KEY'— en vez de mantener dos copias
        del esquema.
        """
        script_sql = script_sql.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY",
        )
        for sentencia in _partir_sentencias(script_sql):
            sentencia = sentencia.strip()
            if sentencia:
                self.execute(sentencia)

    def cursor(self):
        return _CursorDesdeConexion(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        if self._conn is not None:
            self._pool.putconn(self._conn)
            self._conn = None
