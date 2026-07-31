# -*- coding: utf-8 -*-
"""
despertar_web.py — abre la web de solicitudes con un navegador headless
(Playwright) para SACARLA del modo dormido de Streamlit Community Cloud.

Por qué un navegador y no un simple request: cuando la app está dormida,
Streamlit devuelve HTTP 200 con una página estática, pero el proceso Python
NO arranca. Solo un navegador de verdad —que ejecuta el JavaScript y abre el
WebSocket, y de ser necesario aprieta el botón "get this app back up"— logra
que la app se levante. Por eso este script corre en GitHub Actions con
Chromium headless, no como un ping.

La URL sale de la variable de entorno STREAMLIT_APP_URL (se setea en el
workflow desde una variable del repositorio, con un valor por defecto para
no depender de configurar nada).
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("STREAMLIT_APP_URL", "https://insumos-mt26.streamlit.app").strip()
ESPERA_MS = 60000  # cuánto darle a la app para terminar de levantar


def main() -> int:
    print(f"Despertando: {URL}")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        try:
            pagina.goto(URL, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"No se pudo cargar la página: {e}")
            navegador.close()
            return 1

        # Si aparece el botón de "la app está dormida, despertala", apretarlo.
        # El texto exacto puede variar; se busca por "back up" sin distinguir
        # mayúsculas. Si no está (la app ya estaba despierta), se ignora.
        try:
            boton = pagina.get_by_role(
                "button", name=re.compile(r"back up", re.IGNORECASE)
            )
            if boton.count() > 0:
                print("La app estaba dormida: apretando el botón para despertarla.")
                boton.first.click(timeout=8000)
        except Exception as e:
            print(f"(sin botón de despertar, o no se pudo apretar: {e})")

        # Darle tiempo a que el contenedor termine de arrancar.
        pagina.wait_for_timeout(ESPERA_MS)
        navegador.close()
    print("Listo: la app quedó activada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
