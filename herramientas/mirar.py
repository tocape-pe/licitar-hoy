"""Los "ojos" del diseño: abre páginas en Edge (Playwright), toma capturas en
tres anchos y revisa problemas que se ven mal en un celular.

Uso:
  python herramientas/mirar.py http://127.0.0.1:8000 / /oferta/x/ --out capturas
Revisa: scroll horizontal, áreas táctiles menores a 44 px, imágenes sin
width/height (saltos de diseño), errores de consola. Requiere
`pip install -r requirements-dev.txt` (usa el Edge instalado, no descarga
navegadores).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ANCHOS = {"celular": (390, 844), "tablet": (768, 1024), "escritorio": (1440, 900)}

REVISION_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const out = {scrollHorizontal: document.documentElement.scrollWidth > vw + 1, tactilesChicos: [],
               imagenesSinMedidas: [], desbordes: []};
  for (const el of document.querySelectorAll('a, button, input, select, textarea, summary, [role=button]')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(el).visibility === 'hidden') continue;
    // Los enlaces dentro de un párrafo son texto corrido: no se exigen 44 px.
    if (el.tagName === 'A' && el.closest('p, li, dd, td') && !el.matches('[class]')) continue;
    // Enlace "estirado" a toda la tarjeta con un ::after absoluto: el área real es la tarjeta.
    if (getComputedStyle(el, '::after').position === 'absolute' && getComputedStyle(el, '::after').content !== 'none') continue;
    // Checkbox/radio dentro de su etiqueta: cuenta el área de la etiqueta.
    if (el.matches('input[type=checkbox], input[type=radio]') && el.closest('label')) {
      const lr = el.closest('label').getBoundingClientRect();
      if (lr.height >= 44) continue;
    }
    if (r.height < 44 && r.width < 200 || r.height < 32) {
      out.tactilesChicos.push(`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(' ')[0] : ''} `
        + `"${(el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(r.width)}×${Math.round(r.height)}`);
    }
  }
  for (const img of document.querySelectorAll('img')) {
    if (!img.getAttribute('width') || !img.getAttribute('height')) out.imagenesSinMedidas.push(img.src.slice(0, 80));
  }
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && getComputedStyle(el).position !== 'fixed' && r.width < vw * 3) {
      out.desbordes.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} → ${Math.round(r.right)}px`);
      if (out.desbordes.length > 5) break;
    }
  }
  out.tactilesChicos = out.tactilesChicos.slice(0, 8);
  return out;
}
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--out", default="capturas")
    ap.add_argument("--alto-max", type=int, default=2600, help="alto máximo de la captura completa")
    ap.add_argument("--oscuro", action="store_true", help="simular modo oscuro")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    informe = {}
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge")
        for nombre, (w, h) in ANCHOS.items():
            ctx = nav.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                                  is_mobile=nombre == "celular", has_touch=nombre == "celular",
                                  color_scheme="dark" if args.oscuro else "light", locale="es-PE")
            for ruta in args.rutas:
                page = ctx.new_page()
                errores = []
                page.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: errores.append(str(e)))
                page.goto(args.base.rstrip("/") + ruta, wait_until="networkidle")
                page.wait_for_timeout(600)
                alto = min(page.evaluate("document.documentElement.scrollHeight"), args.alto_max)
                slug = re.sub(r"[^a-z0-9]+", "-", ruta.lower()).strip("-") or "portada"
                archivo = out / f"{slug}_{nombre}{'_oscuro' if args.oscuro else ''}.png"
                # sin full_page, Playwright recorta el clip al viewport (solo salía la primera pantalla)
                page.screenshot(path=str(archivo), full_page=True, clip={"x": 0, "y": 0, "width": w, "height": alto})
                r = page.evaluate(REVISION_JS)
                r["errores"] = errores[:5]
                informe[f"{ruta} @ {nombre}"] = r
                problemas = [k for k in ("scrollHorizontal",) if r[k]] + \
                            [f"{k}: {len(r[k])}" for k in ("tactilesChicos", "imagenesSinMedidas", "desbordes", "errores") if r[k]]
                print(f"{ruta:40} {nombre:10} {'OK' if not problemas else ' | '.join(problemas)}  → {archivo.name}")
                page.close()
            ctx.close()
        nav.close()
    (out / "informe.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
