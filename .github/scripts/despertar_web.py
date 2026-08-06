import os
import re
import sys
from playwright.sync_api import sync_playwright

URL = os.environ.get("STREAMLIT_APP_URL", "https://insumos-mt26.streamlit.app").strip()
ESPERA_MS = 60000

def main() -> int:
    print(f"Despertando: {URL}")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        try:
            pagina.goto(URL, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"No se pudo cargar la pagina: {e}")
            navegador.close()
            return 1
        try:
            boton = pagina.get_by_role("button", name=re.compile(r"back up", re.IGNORECASE))
            if boton.count() > 0:
                print("La app estaba dormida: apretando el boton.")
                boton.first.click(timeout=8000)
        except Exception as e:
            print(f"(sin boton de despertar: {e})")
        pagina.wait_for_timeout(ESPERA_MS)
        navegador.close()
    print("Listo: la app quedo activada.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
