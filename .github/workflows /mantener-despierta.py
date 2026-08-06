name: Despertar la web (mañana y mediodía, L a V)

on:
  schedule:
    - cron: "0 9 * * 1-5"
    - cron: "0 15 * * 1-5"
  workflow_dispatch: {}

jobs:
  despertar:
    runs-on: ubuntu-latest
    steps:
      - name: Preparar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Instalar Playwright + Chromium
        run: |
          pip install playwright
          python -m playwright install --with-deps chromium

      - name: Despertar la web
        run: |
          python - <<'PY'
          import os, re
          from playwright.sync_api import sync_playwright
          URL = os.environ.get("STREAMLIT_APP_URL", "https://insumos-mt26.streamlit.app").strip()
          print("Despertando:", URL)
          with sync_playwright() as p:
              navegador = p.chromium.launch()
              pagina = navegador.new_page()
              pagina.goto(URL, wait_until="load", timeout=60000)
              try:
                  boton = pagina.get_by_role("button", name=re.compile(r"back up", re.IGNORECASE))
                  if boton.count() > 0:
                      print("Estaba dormida: apretando el boton.")
                      boton.first.click(timeout=8000)
              except Exception as e:
                  print("(sin boton de despertar:", e, ")")
              pagina.wait_for_timeout(60000)
              navegador.close()
          print("Listo: la app quedo activada.")
          PY
