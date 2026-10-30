"""Descarga los procedimientos recientes del OECE y escribe avisos.json.

Uso: python -m scraper --previous data/avisos.json --output out/avisos.json

Cada corrida pide los convocados en los últimos --dias (por defecto 14:
cubre el plazo de consultas de casi todos y su paso a adjudicado/desierto)
y los fusiona con la corrida anterior. Los avisos que ya salieron de la
ventana se conservan tal cual hasta --retener días desde su publicación
(sus páginas siguen vivas, con noindex, cuando cierran).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .client import Client
from .oece import PORTAL, normalizar, releases, ultima_version

LIMA = timezone(timedelta(hours=-5))


def load_previous(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def deduplicar(avisos: list[dict]) -> list[dict]:
    """Misma entidad + misma nomenclatura = el proceso se anuló (NULO) y se
    relanzó con otro ocid. Queda el publicado más recientemente y anota en
    `reemplaza` los ocid que deja atrás. Ojo: la misma nomenclatura en
    entidades distintas es casualidad (MDH = Huanchaco y Huasmín)."""
    grupos: dict[tuple, list[dict]] = {}
    for a in avisos:
        grupos.setdefault((a["entidad"], a["nomenclatura"]), []).append(a)
    out = []
    for g in grupos.values():
        g.sort(key=lambda a: (a.get("publicado") or "", a.get("version") or ""), reverse=True)
        if len(g) > 1:
            g[0]["reemplaza"] = sorted({oc for a in g[1:] for oc in [a["ocid"], *a.get("reemplaza", [])]})
        out.append(g[0])
    return out


def fusionar(previos: list[dict], nuevos: list[dict], hoy: str, retener: int) -> list[dict]:
    """Los nuevos reemplazan a los previos del mismo ocid; `visto` (primer día
    en que lo vimos) se hereda. Se descartan los publicados hace más de
    `retener` días."""
    out = {a["ocid"]: a for a in previos}
    for a in nuevos:
        a["visto"] = out.get(a["ocid"], {}).get("visto", hoy)
        out[a["ocid"]] = a
    limite = (date.fromisoformat(hoy) - timedelta(days=retener)).isoformat()
    vivos = deduplicar([a for a in out.values() if (a.get("publicado") or hoy)[:10] >= limite])
    # Primero lo que cierra antes; lo que no tiene plazo de consultas, al final.
    vivos.sort(key=lambda a: (a.get("consultas_fin") or "9999", a.get("publicado") or ""))
    return vivos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous")
    ap.add_argument("--output", required=True)
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--retener", type=int, default=60)
    ap.add_argument("--max-paginas", type=int)
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args(argv)

    previous = load_previous(args.previous)
    hoy = datetime.now(LIMA).date()
    desde = (hoy - timedelta(days=args.dias)).isoformat()

    client = Client(delay=args.delay)
    started = time.monotonic()
    vistos, error = [], None
    try:
        for i, r in enumerate(releases(client, desde, hoy.isoformat(), max_paginas=args.max_paginas), 1):
            vistos.append(r)
            if i % 2000 == 0:
                print(f"{i} releases · {client.requests} peticiones", flush=True)
    except Exception as exc:  # se publica lo que haya, completado con lo anterior
        error = f"{type(exc).__name__}: {exc}"
        print(f"ERROR tras {len(vistos)} releases: {error}", file=sys.stderr)

    ultimos = ultima_version(vistos)
    nuevos, basura = [], 0
    for r in ultimos.values():
        a = normalizar(r)
        if a:
            nuevos.append(a)
        else:
            basura += 1
    avisos = fusionar(previous.get("avisos", []), nuevos, hoy.isoformat(), args.retener)

    relanzados = sum(1 for a in avisos if a.get("reemplaza"))
    result = {
        "generatedAt": datetime.now(LIMA).isoformat(timespec="seconds"),
        "source": {
            "name": "Portal de Contrataciones Abiertas del OECE (OCDS)",
            "url": PORTAL,
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "ok": error is None,
            "error": error,
            "desde": desde,
            "hasta": hoy.isoformat(),
            "requests": client.requests,
            "releases": len(vistos),
            "procesos": len(ultimos),
            "descartados": basura,
            "relanzados": relanzados,
            "seconds": round(time.monotonic() - started),
        },
        "avisos": avisos,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    abiertos = sum(1 for a in avisos if a["estado"] == "CONVOCADO")
    print(f"{len(avisos)} avisos ({abiertos} convocados) · {len(ultimos)} procesos en la ventana "
          f"{desde} a {hoy} ·{basura} descartados · {relanzados} relanzados · "
          f"{client.requests} peticiones · ok={error is None}")
    # Falla la corrida solo si no hay nada que publicar.
    return 0 if avisos else 1


if __name__ == "__main__":
    sys.exit(main())
