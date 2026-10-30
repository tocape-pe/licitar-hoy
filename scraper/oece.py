"""API OCDS del OECE (Portal de Contrataciones Abiertas).

Documentación: https://contratacionesabiertas.oece.gob.pe/api (OpenAPI
embebida en el JS del portal). Se usa /releasesAfter: hasta 100 releases
por petición, paginación search-after sin el tope de 10,000 de /releases.

startDate/endDate filtran por la fecha de inicio de la convocatoria. Cada
lote diario (~10:24 Lima) vuelve a publicar una "foto" de cada proceso
activo aunque no haya cambiado, así que un proceso trae varias versiones:
vale la más reciente (`date`).

La API NO trae el cronograma: `enquiryPeriod` es el plazo de consultas
(el portal lo rotula "Fecha de finalización de consultas") y
`tenderPeriod` vale inicio = fin = día de la convocatoria (no se usa).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Iterator
from urllib.parse import urlencode

PORTAL = "https://contratacionesabiertas.oece.gob.pe"
API = f"{PORTAL}/api/v1"
FICHA = f"{PORTAL}/proceso/{{ocid}}"
OBJETOS = {"goods": "Bienes", "services": "Servicios", "works": "Obras"}
# Un ítem en cualquiera de estos estados sigue en carrera.
ABIERTOS = {"CONVOCADO"}


def releases(client, desde: str, hasta: str, size: int = 100,
             max_paginas: int | None = None) -> Iterator[dict]:
    """Recorre todos los releases de SEACE v3 convocados entre `desde` y
    `hasta` (YYYY-MM-DD, ambos incluidos)."""
    url = f"{API}/releasesAfter?" + urlencode(
        {"size": size, "sourceId": "seace_v3", "startDate": desde, "endDate": hasta})
    paginas = 0
    while url:
        data = client.get_json(url)
        paginas += 1
        lote = data.get("releases") or []
        yield from lote
        if not lote or (max_paginas and paginas >= max_paginas):
            return
        url = (data.get("links") or {}).get("next")


def ultima_version(rels: Iterable[dict]) -> dict[str, dict]:
    """Una versión por proceso: la de `date` más reciente."""
    out: dict[str, dict] = {}
    for r in rels:
        oc = r.get("ocid")
        if oc and (oc not in out or (r.get("date") or "") > (out[oc].get("date") or "")):
            out[oc] = r
    return out


def _texto(s) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def objeto(tipo: str, categoria: str | None, descripcion: str) -> str | None:
    """Bienes / Servicios / Obras / Consultoría. OCDS no tiene categoría de
    consultoría: viene como "services" (p. ej. supervisión de obra por
    Concurso Público Abreviado), así que se deduce del tipo o la descripción."""
    if "CONSULTORIA" in _sin_tildes(f"{tipo} {descripcion}").upper():
        return "Consultoría"
    return OBJETOS.get(categoria or "")


def numero_convocatoria(nomenclatura: str) -> int | None:
    """El último tramo de la nomenclatura es el N.° de convocatoria
    (…-SEDAPAR-2 = segunda: la primera quedó desierta o se anuló)."""
    m = re.search(r"-(\d{1,2})$", nomenclatura)
    return int(m.group(1)) if m else None


def _monto(v) -> float | None:
    """0.0 = no publicado (pasa en ~57 % de bienes/servicios); nunca 0."""
    amount = (v or {}).get("amount")
    return float(amount) if amount else None


def estado(estados_items: list[str]) -> str | None:
    unicos = sorted(set(e for e in estados_items if e))
    if not unicos:
        return None
    if ABIERTOS & set(unicos):
        return "CONVOCADO"
    return unicos[0] if len(unicos) == 1 else "VARIOS"


def normalizar(r: dict) -> dict | None:
    """Release OCDS -> aviso. None si es basura (sin nomenclatura,
    descripción o entidad)."""
    t = r.get("tender") or {}
    ocid = r.get("ocid")
    nomenclatura = _texto(t.get("title"))
    descripcion = _texto(t.get("description"))
    ent = t.get("procuringEntity") or r.get("buyer") or {}
    entidad = _texto(ent.get("name"))
    if not (ocid and nomenclatura and entidad) or len(descripcion) < 5:
        return None

    parte = next((p for p in r.get("parties") or [] if p.get("id") == ent.get("id")), {})
    direccion = parte.get("address") or {}
    ruc = next((i.get("id") for i in parte.get("additionalIdentifiers") or []
                if i.get("scheme") == "PE-RUC"), None)

    items = []
    for i in t.get("items") or []:
        unspsc = next((c for c in i.get("additionalClassifications") or []
                       if c.get("scheme") == "UNSPSC"), {})
        cubso = i.get("classification") or {}
        items.append({
            "descripcion": _texto(i.get("description")),
            "cantidad": i.get("quantity"),
            "unidad": (i.get("unit") or {}).get("name"),
            "monto": _monto(i.get("totalValue")),
            "estado": i.get("statusDetails"),
            "cubso": cubso.get("id") if cubso.get("scheme") == "CUBSO" else None,
            "unspsc": unspsc.get("id"),
            "unspsc_desc": unspsc.get("description"),
        })

    adjudicaciones = []
    for a in r.get("awards") or []:
        for s in a.get("suppliers") or []:
            adjudicaciones.append({
                "proveedor": _texto(s.get("name")),
                "ruc": (s.get("id") or "").removeprefix("PE-RUC-") or None,
                "monto": _monto(a.get("value")),
                "fecha": (a.get("date") or "")[:10] or None,
            })

    tipo = _texto(t.get("procurementMethodDetails"))
    consultas = t.get("enquiryPeriod") or {}
    return {
        "ocid": ocid,
        "id": str(t.get("id") or ""),
        "nomenclatura": nomenclatura,
        "convocatoria_n": numero_convocatoria(nomenclatura),
        "descripcion": descripcion,
        "entidad": entidad,
        "entidad_ruc": ruc,
        "departamento": _texto(direccion.get("department")) or None,
        "provincia": _texto(direccion.get("region")) or None,
        "distrito": _texto(direccion.get("locality")) or None,
        "tipo": tipo or None,
        "objeto": objeto(tipo, t.get("mainProcurementCategory"), descripcion),
        "monto": _monto(t.get("value")),
        "moneda": (t.get("value") or {}).get("currency"),
        "publicado": t.get("datePublished"),
        "consultas_inicio": consultas.get("startDate"),
        "consultas_fin": consultas.get("endDate"),
        "estado": estado([i["estado"] for i in items]),
        "postores": t.get("numberOfTenderers"),
        "items": items,
        "adjudicaciones": adjudicaciones,
        "documentos": [{
            "titulo": _texto(d.get("title")),
            "url": d.get("url"),
            "fecha": d.get("datePublished"),
            "formato": d.get("format"),
        } for d in t.get("documents") or [] if d.get("url")],
        "version": r.get("date"),
        "url": FICHA.format(ocid=ocid),
    }
