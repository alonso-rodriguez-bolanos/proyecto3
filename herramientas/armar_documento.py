"""Junta las secciones de docs/ en un solo documento técnico: docs/documento_tecnico.md, .html y .pdf.

Uso: python herramientas/armar_documento.py
El PDF se genera con Microsoft Edge o Google Chrome en modo headless; si no hay ninguno, quedan el .md y el .html.
"""

import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent.parent / "docs"
SALIDA = DOCS / "documento_tecnico"

PORTADA = {
    "institucion": "Instituto Tecnológico de Costa Rica — Campus San Carlos",
    "curso": "IC3101 Arquitectura de Computadoras",
    "titulo": "III Proyecto: Web Scraping Multinúcleo y Sitio Web",
    "subtitulo": "Documento técnico",
    "integrantes": ["Andrew Arce Pérez", "Alonso Rodríguez Bolaños", "Daniel Rojas Vargas"],
    "url": "https://alonso-rodriguez-bolanos.github.io/proyecto3/",
    "repo": "https://github.com/alonso-rodriguez-bolanos/proyecto3",
}

SECCIONES = [
    "seccion1_arquitectura.md",
    "seccion2_repo.md",
    "seccion3_tiendas.md",
    "seccion3_metacritic_hltb.md",
    "seccion4_actualizacion.md",
    "seccion5_rendimiento.md",
    "seccion6_instalacion.md",
]

ESTILO = """
@page { size: Letter; margin: 2cm 2cm 2.2cm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1e293b; }
h1 { font-size: 19pt; color: #0f172a; border-bottom: 3px solid #22c55e; padding-bottom: 4px; margin-top: 0; page-break-before: always; }
h2 { font-size: 13.5pt; color: #0f172a; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 11.5pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.3pt; page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 5px 7px; text-align: left; vertical-align: top; }
th { background: #f1f5f9; }
code { font-family: Consolas, monospace; font-size: 9pt; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
pre { background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 6px; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%; display: block; margin: 12px auto; page-break-inside: avoid; }
img[src$="png"] { max-width: 78%; }
blockquote { border-left: 4px solid #22c55e; margin: 10px 0; padding: 4px 12px; color: #475569; background: #f8fafc; }
.portada { text-align: center; padding-top: 5cm; }
.portada h1 { border: none; page-break-before: avoid; font-size: 24pt; }
.portada .sub { font-size: 15pt; color: #16a34a; margin: 8px 0 3cm; }
.portada p { margin: 4px 0; }
.indice { page-break-before: always; }
.indice h1 { page-break-before: avoid; }
.indice ol { font-size: 11pt; line-height: 2; }
"""


def portada_md() -> str:
    datos = PORTADA
    integrantes = "".join(f"<p>{nombre}</p>" for nombre in datos["integrantes"])
    return f"""<div class="portada">
<p>{datos['institucion']}</p>
<p>{datos['curso']}</p>
<h1>{datos['titulo']}</h1>
<p class="sub">{datos['subtitulo']}</p>
{integrantes}
<p style="margin-top:2cm">Sitio público: {datos['url']}</p>
<p>Repositorio: {datos['repo']}</p>
<p>{date.today().strftime('%d/%m/%Y')}</p>
</div>

<div class="indice" markdown="1">

# Contenido

1. Arquitectura de la solución
2. Estructura del REPO y cómo se actualiza
3. Estrategia de web scraping por sitio e indicador de oferta
4. Manejo de errores y actualización recurrente
5. Análisis de rendimiento
6. Instalación, uso y URL pública

</div>
"""


def unir() -> str:
    partes = [portada_md()]
    for nombre in SECCIONES:
        texto = (DOCS / nombre).read_text(encoding="utf-8").strip()
        if nombre == "seccion3_metacritic_hltb.md":
            # la sección 3 viene en dos archivos: el segundo no repite el título principal
            primera, _, resto = texto.partition("\n")
            texto = "## " + primera.lstrip("# ").split(": ", 1)[-1].strip() + "\n" + resto
        partes.append(texto)
    return "\n\n".join(partes) + "\n"


def buscar_navegador() -> str | None:
    candidatos = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for ruta in candidatos:
        if Path(ruta).exists():
            return ruta
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("msedge")


def main() -> None:
    texto = unir()
    SALIDA.with_suffix(".md").write_text(texto, encoding="utf-8")
    cuerpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "md_in_html"])
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>{PORTADA['titulo']}</title><style>{ESTILO}</style></head><body>{cuerpo}</body></html>"""
    ruta_html = SALIDA.with_suffix(".html")
    ruta_html.write_text(html, encoding="utf-8")
    print("listo:", SALIDA.with_suffix(".md").name, ruta_html.name)

    navegador = buscar_navegador()
    if not navegador:
        print("no se encontró Edge ni Chrome; abre el .html y usa Imprimir → Guardar como PDF")
        return
    ruta_pdf = SALIDA.with_suffix(".pdf")
    ruta_pdf.unlink(missing_ok=True)
    perfil = Path(__file__).resolve().parent.parent / "logs" / "perfil_pdf"
    subprocess.run([navegador, "--headless", "--disable-gpu", f"--user-data-dir={perfil}", "--no-pdf-header-footer",
                    f"--print-to-pdf={ruta_pdf}", ruta_html.resolve().as_uri()],
                   check=False, capture_output=True, timeout=120)
    for _ in range(60):  # en Windows el navegador puede terminar de escribir después de devolver el control
        if ruta_pdf.exists() and ruta_pdf.stat().st_size > 0:
            break
        time.sleep(0.5)
    print("PDF:", ruta_pdf.name if ruta_pdf.exists() else "no se pudo generar")


if __name__ == "__main__":
    sys.exit(main())
