"""Genera el sitio estático de Licitar Hoy a partir de avisos.json.

Uso: python site/build.py --data out/avisos.json --out public [--state state.json]

El patrón es el de Chamba al Toque (site/build.py): una página por aviso,
listados por objeto, rubro, departamento, entidad y rango de monto, slugs
congelados en state.json, avisos cerrados con noindex, sitemaps con lastmod
real y una salvaguarda que no publica si los datos caen a menos de la mitad.

Datos honestos: la API del OECE no trae la fecha de presentación de ofertas
ni la buena pro, solo el plazo de consultas; lo que no viene se muestra
vacío y se manda a la ficha oficial.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import textos as T  # noqa: E402

LIMA = timezone(timedelta(hours=-5))
BASE_URL = "https://licitarhoy.toca.pe"
MARCA = "Licitar Hoy"
CONTACTO = "3b3n3z3r333@gmail.com"  # único medio de contacto público
FUENTE = "Portal de Contrataciones Abiertas del OECE"
FUENTE_URL = "https://contratacionesabiertas.oece.gob.pe"
LICENCIA_URL = "https://creativecommons.org/licenses/by/4.0/deed.es"
SEACE_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"

POR_PAGINA = 25
UMBRAL_ENTIDAD = 3
UMBRAL_RUBRO = 10
DIAS_VIGENTE = 45  # un "CONVOCADO" publicado hace más que esto ya no se ofrece como abierto
MIN_PROPORCION = 0.5  # salvaguarda: no publicar si llega menos de la mitad
PORTADA_ULTIMAS = 24
DIAS_URGENTE = 3
# No son oportunidades abiertas a cualquier proveedor.
TIPOS_EXCLUIDOS = {"Convenio", "Contratación Directa"}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

DEPARTAMENTOS = {
    "AMAZONAS": "Amazonas", "ANCASH": "Áncash", "APURIMAC": "Apurímac", "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho", "CAJAMARCA": "Cajamarca", "CALLAO": "Callao", "CUSCO": "Cusco",
    "HUANCAVELICA": "Huancavelica", "HUANUCO": "Huánuco", "ICA": "Ica", "JUNIN": "Junín",
    "LA LIBERTAD": "La Libertad", "LAMBAYEQUE": "Lambayeque", "LIMA": "Lima", "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios", "MOQUEGUA": "Moquegua", "PASCO": "Pasco", "PIURA": "Piura",
    "PUNO": "Puno", "SAN MARTIN": "San Martín", "TACNA": "Tacna", "TUMBES": "Tumbes",
    "UCAYALI": "Ucayali",
}

OBJETOS = {
    "Bienes": {"slug": "bienes", "titulo": "Licitaciones de bienes", "intro":
               "Compras de bienes del Estado: alimentos, combustible, medicinas, equipos, mobiliario y más."},
    "Servicios": {"slug": "servicios", "titulo": "Licitaciones de servicios", "intro":
                  "Servicios que contratan las entidades públicas: mantenimiento, limpieza, vigilancia, "
                  "transporte, alquileres y más."},
    "Obras": {"slug": "obras", "titulo": "Licitaciones de obras", "intro":
              "Obras públicas convocadas por municipalidades, gobiernos regionales y otras entidades: "
              "pistas, colegios, agua y saneamiento, puentes y más."},
    "Consultoría": {"slug": "consultoria", "titulo": "Concursos de consultoría", "intro":
                    "Consultorías de obra (expedientes técnicos y supervisión) y otras consultorías "
                    "que contrata el Estado."},
}

RANGOS = [
    {"slug": "hasta-100-mil", "nombre": "Hasta S/ 100 mil", "min": 0, "max": 100_000},
    {"slug": "100-mil-a-500-mil", "nombre": "De S/ 100 mil a S/ 500 mil", "min": 100_000, "max": 500_000},
    {"slug": "500-mil-a-2-millones", "nombre": "De S/ 500 mil a S/ 2 millones", "min": 500_000, "max": 2_000_000},
    {"slug": "mas-de-2-millones", "nombre": "Más de S/ 2 millones", "min": 2_000_000, "max": float("inf")},
]

# Tipos de procedimiento de la Ley 32069 en palabras simples (solo lo que dice la ley).
TIPOS_TXT = {
    "Licitación Pública": "procedimiento para bienes y obras de mayor monto",
    "Licitación Pública Abreviada": "procedimiento con plazos más cortos para bienes y obras",
    "Concurso Público de Servicios": "procedimiento para servicios de mayor monto",
    "Concurso Público Abreviado": "procedimiento con plazos más cortos para servicios y consultorías",
    "Concurso Público para Consultoría": "procedimiento para consultorías",
    "Subasta Inversa Electrónica": "gana el menor precio entre quienes cumplen la ficha técnica",
    "Comparación de Precios": "procedimiento simple para bienes y servicios comunes",
}

# Páginas informativas. lastmod: cambiarlo al editar el texto de la plantilla.
INFO = [
    {"slug": "acerca", "title": f"Acerca de {MARCA}", "h1": f"Acerca de {MARCA}", "indexable": True,
     "lastmod": "2026-10-29",
     "desc": f"Qué es {MARCA}, de dónde salen las licitaciones (datos abiertos del OECE), qué datos no "
             "trae la fuente y cada cuánto se actualiza."},
    {"slug": "aviso-legal", "title": f"Aviso legal | {MARCA}", "h1": "Aviso legal", "indexable": True,
     "lastmod": "2026-10-29",
     "desc": f"Datos abiertos del OECE con licencia CC BY 4.0. {MARCA} no es una entidad del Estado, "
             "no cobra y no intermedia en las contrataciones."},
    {"slug": "privacidad", "title": f"Privacidad | {MARCA}", "h1": "Privacidad", "indexable": False,
     "lastmod": "2026-10-29",
     "desc": f"{MARCA} no pide datos personales. Visitas contadas sin cookies."},
]


# ---------------------------------------------------------------- formato

def _d(iso: str | None) -> date | None:
    return date.fromisoformat(iso[:10]) if iso else None


def fecha_larga(iso: str | None) -> str:
    d = _d(iso)
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}" if d else ""


def fecha_corta(iso: str | None) -> str:
    d = _d(iso)
    return f"{d.day} de {MESES[d.month - 1]}" if d else ""


def fecha_dia(iso: str | None) -> str:
    """'lunes 2 de noviembre'."""
    d = _d(iso)
    return f"{DIAS_SEMANA[d.weekday()]} {d.day} de {MESES[d.month - 1]}" if d else ""


def soles(n: float | None, decimales: bool = True) -> str:
    if not n:
        return ""
    if not decimales or float(n).is_integer():
        return f"S/ {n:,.0f}"
    return f"S/ {n:,.2f}"


def soles_corto(n: float) -> str:
    """'S/ 3.4 millones', 'S/ 222 mil' (títulos y tarjetas de resumen)."""
    if n >= 1_000_000:
        return f"S/ {n / 1_000_000:,.1f} millones".replace(".0 ", " ")
    if n >= 1_000:
        return f"S/ {n / 1_000:,.0f} mil"
    return soles(n, False)


def miles(n: int) -> str:
    return f"{n:,}"


def plural(n: int, uno: str, varios: str) -> str:
    return f"{miles(n)} {uno if n == 1 else varios}"


def cortar(texto: str, maximo: int) -> str:
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) <= maximo:
        return texto
    corte = texto[:maximo].rsplit(" ", 1)[0].rstrip(",;:")
    return corte if corte.endswith(".") else corte + "…"


def armar(frases: list[str], maximo: int = 155) -> str:
    """Junta frases completas en orden de prioridad mientras quepan; nunca
    corta una frase a la mitad (salvo la primera, si sola no cabe)."""
    frases = [f for f in frases if f]
    if not frases:
        return ""
    out = [frases[0] if len(frases[0]) <= maximo else cortar(frases[0], maximo)]
    for f in frases[1:]:
        if len(" ".join(out + [f])) <= maximo:
            out.append(f)
    return " ".join(out)


def consultas_texto(dias: int | None, fin: str | None) -> str:
    if dias is None:
        return ""
    if dias < 0:
        return f"Consultas cerradas el {fecha_corta(fin)}"
    if dias == 0:
        return "Consultas hasta hoy"
    if dias == 1:
        return "Consultas hasta mañana"
    if dias <= 7:
        return f"Consultas hasta el {fecha_dia(fin)}"
    return f"Consultas hasta el {fecha_corta(fin)}"


def con_articulo(entidad: str) -> str:
    """'Municipalidad Distrital de X' -> 'la Municipalidad Distrital de X'."""
    w = entidad.split(" ")[0].lower() if entidad else ""
    femeninas = {"municipalidad", "universidad", "dirección", "superintendencia", "unidad",
                 "autoridad", "oficina", "red", "contraloría", "defensoría", "procuraduría",
                 "beneficencia", "sociedad", "empresa", "corte", "fiscalía", "presidencia",
                 "agencia", "escuela", "comisión", "junta", "gerencia", "zona", "intendencia",
                 "marina", "fuerza", "policía", "caja", "sede"}
    masculinos = {"gobierno", "ministerio", "hospital", "instituto", "seguro", "servicio",
                  "programa", "poder", "banco", "fondo", "organismo", "centro", "consejo",
                  "proyecto", "tribunal", "jurado", "registro", "archivo", "despacho", "ejército"}
    if w in femeninas:
        return "la " + entidad
    if w in masculinos:
        return "el " + entidad
    return entidad


def de_articulo(entidad: str) -> str:
    """'de la Municipalidad...', 'del Ministerio...' (nunca 'de el')."""
    con = con_articulo(entidad)
    return "del " + con[3:] if con.startswith("el ") else "de " + con


# ---------------------------------------------------------------- estado

def cargar_json(path: Path, defecto):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defecto


def hash_contenido(a: dict) -> str:
    campos = ("nomenclatura", "descripcion", "entidad", "tipo", "monto", "consultas_inicio", "consultas_fin",
              "estado", "items", "adjudicaciones", "documentos", "postores")
    raw = json.dumps([a.get(k) for k in campos], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- modelo

class Sitio:
    def __init__(self, data: dict, state: dict, base_url: str, hoy: date, ahora: datetime):
        self.base_url = base_url.rstrip("/")
        self.base_path = urlparse(self.base_url).path.rstrip("/")
        self.hoy = hoy
        self.ahora = ahora
        self.anio = hoy.year
        self.state = state
        for k in ("avisos", "entidades", "entidad_slugs", "listados"):
            self.state.setdefault(k, {})
        self.generado = data.get("generatedAt") or ahora.isoformat(timespec="seconds")
        self.fuente = data.get("source", {})
        self.errores: list[str] = []
        self.paginas: list[dict] = []  # para sitemaps: {path, lastmod, indexable}

        self.excluidos = 0
        todos = []
        for a in data.get("avisos", []):
            if a.get("tipo") in TIPOS_EXCLUIDOS:
                self.excluidos += 1
                continue
            todos.append(self.preparar(a))

        limite = (hoy - timedelta(days=DIAS_VIGENTE)).isoformat()
        self.vigentes = [a for a in todos if a["estado"] == "CONVOCADO" and (a.get("publicado") or "")[:10] >= limite]
        ids = {a["ocid"] for a in self.vigentes}
        self.cerrados = [a for a in todos if a["ocid"] not in ids]
        for a in self.cerrados:
            a["cerrado"] = True
        # Lo que hay que mirar primero: consultas abiertas que cierran antes; luego
        # las de consultas ya cerradas (aún en carrera) y al final sin plazo.
        self.vigentes.sort(key=lambda a: (0 if a["dias"] is not None and a["dias"] >= 0 else
                                          1 if a["dias"] is not None else 2,
                                          a["dias"] if a["dias"] is not None and a["dias"] >= 0 else 0,
                                          -(a["monto"] or 0)))
        self.abiertos = [a for a in self.vigentes if a["dias"] is not None and a["dias"] >= 0]

        self.por_dep = defaultdict(list)
        self.por_entidad = defaultdict(list)
        self.por_objeto = defaultdict(list)
        self.por_rubro = defaultdict(list)
        self.por_rango = defaultdict(list)
        for a in self.vigentes:
            self.por_dep[a["dep_slug"]].append(a)
            self.por_entidad[a["entidad_slug"]].append(a)
            if a["objeto"]:
                self.por_objeto[a["objeto"]].append(a)
            for r in a["rubros"]:
                self.por_rubro[r].append(a)
            if a["rango"]:
                self.por_rango[a["rango"]].append(a)

        # Entidades indexables con histéresis: entran con 3+, salen solo al quedar en 0.
        self.entidad_indexable = {}
        for s, lista in self.por_entidad.items():
            st = self.state["entidades"].setdefault(s, {})
            idx = len(lista) >= UMBRAL_ENTIDAD or (st.get("indexable") and len(lista) > 0)
            st["indexable"] = bool(idx)
            self.entidad_indexable[s] = bool(idx)
        for s in list(self.state["entidades"]):
            if s not in self.por_entidad:
                del self.state["entidades"][s]

        # Slugs congelados: se olvidan solo cuando el aviso sale de los datos.
        presentes = {a["ocid"] for a in todos}
        for oc in list(self.state["avisos"]):
            if oc not in presentes:
                del self.state["avisos"][oc]

    # -- URLs
    def url(self, path: str) -> str:
        return self.base_path + path

    def abs(self, path: str) -> str:
        return self.base_url + path

    def entidad_slug(self, nombre_upper: str, nombre_txt: str) -> str:
        slugs = self.state["entidad_slugs"]
        if nombre_upper in slugs:
            return slugs[nombre_upper]
        base = T.slug(nombre_txt, 90)
        usados = set(slugs.values())
        s, n = base, 2
        while s in usados:
            s, n = f"{base}-{n}", n + 1
        slugs[nombre_upper] = s
        return s

    def preparar(self, a: dict) -> dict:
        p = dict(a)
        p["entidad_txt"] = T.nombre_propio(T.normalizar_entidad(a["entidad"]))
        p["entidad_slug"] = self.entidad_slug(a["entidad"].upper(), p["entidad_txt"])
        dep = (a.get("departamento") or "").upper().strip()
        p["dep_txt"] = DEPARTAMENTOS.get(dep, T.nombre_propio(dep) or "Perú")
        p["dep_slug"] = T.slug(p["dep_txt"])
        prov = T.nombre_propio(a.get("provincia") or "")
        p["lugar_txt"] = p["dep_txt"] if not prov or prov.upper() == p["dep_txt"].upper() else f"{prov}, {p['dep_txt']}"
        p["descripcion_txt"] = T.capitalizar_lugares(T.oracion(T.limpiar(a["descripcion"])))
        p["corta"] = T.descripcion_corta(a["descripcion"])
        p["monto_txt"] = soles(a.get("monto"))
        p["rango"] = next((r["slug"] for r in RANGOS if a.get("monto") and r["min"] < a["monto"] <= r["max"]), None)
        p["rubros"] = T.rubros([i.get("unspsc") for i in a.get("items") or []])
        p["tipo_txt"] = TIPOS_TXT.get(a.get("tipo") or "", "")
        p["dias"] = (_d(a["consultas_fin"]) - self.hoy).days if a.get("consultas_fin") else None
        p["consultas_txt"] = consultas_texto(p["dias"], a.get("consultas_fin"))
        p["urgente"] = p["dias"] is not None and 0 <= p["dias"] <= DIAS_URGENTE
        p["segunda"] = (a.get("convocatoria_n") or 1) >= 2
        p["items_txt"] = [{**i, "descripcion_txt": T.capitalizar_lugares(T.oracion(T.limpiar(i.get("descripcion")))),
                           "cantidad_txt": (f"{i['cantidad']:,.0f}" if float(i["cantidad"]).is_integer()
                                            else f"{i['cantidad']:,.2f}") + f" {(i.get('unidad') or '').lower()}"
                                           if i.get("cantidad") else "",
                           "monto_txt": soles(i.get("monto"))} for i in a.get("items") or []]
        # Un solo ítem que repite la descripción del procedimiento: no se repite el texto.
        p["item_repite"] = (len(p["items_txt"]) == 1
                            and p["items_txt"][0]["descripcion_txt"][:60] == p["descripcion_txt"][:60])
        p["adjudicaciones_txt"] = [{**x, "proveedor_txt": T.nombre_propio(x["proveedor"]),
                                    "monto_txt": soles(x.get("monto"))} for x in a.get("adjudicaciones") or []]
        p["cerrado"] = False

        st = self.state["avisos"].get(a["ocid"])
        h = hash_contenido(a)
        hoy = self.hoy.isoformat()
        if not st:
            st = {"slug": T.slug_aviso(p["corta"], p["entidad_txt"], a["id"] or a["ocid"].rsplit("-", 1)[-1]),
                  "first_seen": hoy, "lastmod": hoy, "hash": h}
            self.state["avisos"][a["ocid"]] = st
        elif st.get("hash") != h:
            st["hash"], st["lastmod"] = h, hoy
        p["slug"], p["lastmod"], p["first_seen"] = st["slug"], st["lastmod"], st["first_seen"]
        p["path"] = f"/licitacion/{p['slug']}/"
        return p

    # -- textos generados con datos
    def resumen(self, avisos: list[dict]) -> dict:
        montos = [a["monto"] for a in avisos if a.get("monto")]
        top = Counter(a["entidad_slug"] for a in avisos).most_common(3)
        nombres = {a["entidad_slug"]: a["entidad_txt"] for a in avisos}
        return {
            "n": len(avisos),
            "abiertos": sum(1 for a in avisos if a["dias"] is not None and a["dias"] >= 0),
            "semana": sum(1 for a in avisos if a["dias"] is not None and 0 <= a["dias"] <= 7),
            "con_monto": len(montos),
            "suma": sum(montos),
            "suma_txt": soles_corto(sum(montos)) if montos else "",
            "max_txt": soles_corto(max(montos)) if montos else "",
            "top": [{"nombre": nombres[s], "slug": s, "n": n,
                     "indexable": self.entidad_indexable.get(s, False)} for s, n in top],
        }

    def similares(self, a: dict, n: int = 6) -> list[dict]:
        vistos, out = {a["ocid"]}, []
        candidatos = (
            [x for x in self.por_dep.get(a["dep_slug"], []) if set(x["rubros"]) & set(a["rubros"])],
            [x for x in self.por_dep.get(a["dep_slug"], []) if x["objeto"] == a["objeto"]],
            [x for r in a["rubros"] for x in self.por_rubro.get(r, [])],
        )
        for grupo in candidatos:
            for x in grupo:
                if x["ocid"] not in vistos and x["dias"] is not None and x["dias"] >= 0:
                    vistos.add(x["ocid"])
                    out.append(x)
                    if len(out) >= n:
                        return out
        return out

    # -- JSON-LD
    def demanda(self, a: dict) -> dict:
        """schema.org/Demand: "anuncio público de una organización que busca
        cierto tipo de bienes o servicios". Es lo honesto para una licitación
        (no hay un tipo de Google para esto; no se fuerza JobPosting ni Event)."""
        ld = {
            "@context": "https://schema.org", "@type": "Demand",
            "name": f"{a['nomenclatura']}: {cortar(a['descripcion_txt'], 110)}",
            "description": cortar(a["descripcion_txt"], 500),
            "url": self.abs(a["path"]),
            "identifier": a["nomenclatura"],
            "seller": {"@type": "GovernmentOrganization", "name": a["entidad_txt"],
                       **({"taxID": a["entidad_ruc"]} if a.get("entidad_ruc") else {})},
            "areaServed": {"@type": "AdministrativeArea", "name": f"{a['dep_txt']}, Perú"},
            "availabilityStarts": a.get("publicado"),
            "sameAs": a["url"],
        }
        if a.get("monto"):
            ld["priceSpecification"] = {"@type": "PriceSpecification", "price": a["monto"],
                                        "priceCurrency": a.get("moneda") or "PEN"}
        return ld

    def breadcrumbs(self, items: list[tuple[str, str | None]]) -> dict:
        return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, **({"item": self.abs(p)} if p else {})}
            for i, (n, p) in enumerate(items, 1)]}


# ---------------------------------------------------------------- render

def minificar_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


def ld_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def titulo_aviso(a: dict, limite: int = 70) -> str:
    """'Licitación de [qué] – [entidad] – [departamento]'; si no cabe, se
    sacrifica primero el departamento y luego se acorta el qué."""
    que = a["corta"]
    for t in (f"Licitación de {que} – {a['entidad_txt']} – {a['dep_txt']}",
              f"Licitación de {que} – {a['entidad_txt']}",
              f"Licitación de {T.descripcion_corta(a['descripcion'], 35)} – {a['entidad_txt']}"):
        if len(t) <= limite:
            return t
    return cortar(f"Licitación de {que} – {a['entidad_txt']}", limite)


def construir(sitio: Sitio, out: Path) -> None:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    css = minificar_css((HERE / "static" / "estilos.css").read_text(encoding="utf-8-sig"))
    departamentos = sorted(({"nombre": v[0]["dep_txt"], "slug": k, "n": len(v), "path": f"/departamento/{k}/"}
                            for k, v in sitio.por_dep.items()), key=lambda d: d["nombre"])
    objetos = [{"nombre": nombre, **o, "n": len(sitio.por_objeto.get(nombre, [])), "path": f"/objeto/{o['slug']}/"}
               for nombre, o in OBJETOS.items()]
    rubros = [{**r, "n": len(sitio.por_rubro.get(r["slug"], [])), "path": f"/rubro/{r['slug']}/"}
              for r in T.RUBROS]
    rubros = sorted((r for r in rubros if r["n"]), key=lambda r: -r["n"])
    rangos = [{**r, "n": len(sitio.por_rango.get(r["slug"], [])), "path": f"/monto/{r['slug']}/"} for r in RANGOS]
    actualizado = datetime.fromisoformat(sitio.generado)
    env.globals.update(
        url=sitio.url, abs=sitio.abs, anio=sitio.anio, ld_json=ld_json, miles=miles, plural=plural,
        fecha_larga=fecha_larga, fecha_corta=fecha_corta, soles=soles, departamentos=departamentos,
        objetos=objetos, rubros=rubros, rangos=rangos, css=css, contacto=CONTACTO, marca=MARCA,
        fuente=FUENTE, fuente_url=FUENTE_URL, licencia_url=LICENCIA_URL, seace_url=SEACE_URL,
        hoy=sitio.hoy.isoformat(),
        actualizado_txt=f"{fecha_larga(actualizado.date().isoformat())}, {actualizado:%H:%M}",
        total_vigentes=len(sitio.vigentes), total_abiertos=len(sitio.abiertos),
        entidad_indexable=sitio.entidad_indexable, con_articulo=con_articulo, de_articulo=de_articulo,
        rubro_nombre={r["slug"]: r["nombre"] for r in T.RUBROS},
        reportar=lambda a: (f"mailto:{CONTACTO}?subject=" + quote(f"Reporte: {a['nomenclatura']}") + "&body="
                            + quote(f"Aviso: {sitio.abs(a['path'])}\nNomenclatura: {a['nomenclatura']}\n\n"
                                    "Qué está mal:\n")),
    )

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    def escribir(path: str, plantilla: str, indexable: bool, lastmod: str | None = None, **ctx):
        html = env.get_template(plantilla).render(path=path, canonical=sitio.abs(path), indexable=indexable, **ctx)
        rel = path.strip("/")
        destino = (out / rel / "index.html") if path.endswith("/") else (out / rel)
        if out.resolve() not in destino.resolve().parents:
            raise RuntimeError(f"ruta fuera del sitio: {path}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(html, encoding="utf-8")
        sitio.paginas.append({"path": path, "indexable": indexable, "lastmod": lastmod, "plantilla": plantilla})

    def lastmod_listado(clave: str, avisos: list[dict]) -> str:
        h = hashlib.sha1(",".join(a["ocid"] + a["lastmod"] for a in avisos).encode()).hexdigest()[:16]
        st = sitio.state["listados"].setdefault(clave, {})
        if st.get("hash") != h:
            st["hash"], st["lastmod"] = h, sitio.hoy.isoformat()
        return st["lastmod"]

    def listado(path: str, avisos: list[dict], indexable: bool, titulo: str, h1: str, descripcion: str,
                migas: list, intro: str = "", extra: dict | None = None):
        paginas = max(1, math.ceil(len(avisos) / POR_PAGINA))
        lm = lastmod_listado(path, avisos)
        for n in range(1, paginas + 1):
            p = path if n == 1 else f"{path}pagina/{n}/"
            trozo = avisos[(n - 1) * POR_PAGINA:n * POR_PAGINA]
            desc_n = descripcion if n == 1 else armar([descripcion.split(". ")[0] + ".", f"Página {n}."])
            escribir(p, "listado.html", indexable, lm if n == 1 else None,
                     titulo=titulo + (f" (página {n})" if n > 1 else ""), h1=h1, descripcion=desc_n,
                     avisos=trozo, pagina=n, paginas=paginas, base_listado=path, migas=migas,
                     intro=intro if n == 1 else "", extra=extra or {}, total=len(avisos),
                     resumen=sitio.resumen(avisos), ld=[sitio.breadcrumbs(migas)])

    def con_marca(titulo: str, limite: int = 65) -> str:
        return f"{titulo} | {MARCA}" if len(titulo) + len(MARCA) + 3 <= limite else titulo

    def elegir(*candidatos: str, limite: int = 70) -> str:
        """El primer título que quepa (los primeros llevan más datos), con la marca si entra."""
        candidatos = [c for c in candidatos if c]
        return con_marca(next((c for c in candidatos if len(c) <= limite), candidatos[-1]))

    hoy_txt = fecha_corta(sitio.hoy.isoformat())
    fin_semana = (sitio.hoy + timedelta(days=7)).isoformat()
    semana = [a for a in sitio.abiertos if a["consultas_fin"][:10] <= fin_semana]

    # Portada
    r_all = sitio.resumen(sitio.vigentes)
    escribir("/", "portada.html", True, sitio.vigentes[0]["lastmod"] if sitio.vigentes else None,
             titulo=f"Licitaciones del Estado peruano hoy {sitio.anio}: obras, bienes y servicios | {MARCA}",
             descripcion=armar([f"{plural(len(sitio.vigentes), 'licitación vigente', 'licitaciones vigentes')} "
                                "del Estado peruano para pymes y proveedores, ordenadas por fecha límite de consultas.",
                                f"Datos abiertos del OECE al {hoy_txt}."]),
             h1="Licitaciones del Estado peruano para tu empresa",
             semana=semana[:PORTADA_ULTIMAS], n_semana=len(semana), resumen=r_all,
             ld=[{"@context": "https://schema.org", "@type": "WebSite", "name": MARCA,
                  "url": sitio.abs("/"), "inLanguage": "es-PE"},
                 {"@context": "https://schema.org", "@type": "Organization", "name": MARCA,
                  "url": sitio.abs("/")}])

    # Avisos (vigentes indexables; cerrados con noindex y sin datos estructurados).
    # Misma entidad y misma descripción en varios procedimientos: el título lleva
    # la nomenclatura para que cada página sea distinta.
    repetidos = Counter(titulo_aviso(a) for a in sitio.vigentes)
    for a in sitio.vigentes + sitio.cerrados:
        idx_ent = sitio.entidad_indexable.get(a["entidad_slug"], False)
        migas = [("Inicio", "/"), (a["dep_txt"], f"/departamento/{a['dep_slug']}/")]
        if idx_ent and not a["cerrado"]:
            migas.append((a["entidad_txt"], f"/entidad/{a['entidad_slug']}/"))
        migas.append((a["nomenclatura"], None))
        h1 = f"Licitación de {a['corta']}"
        if a["cerrado"]:
            titulo = cortar(f"{a['nomenclatura']} – {a['entidad_txt']} ({(a['estado'] or 'cerrado').lower()})", 70)
        elif repetidos[titulo_aviso(a)] > 1:
            titulo = cortar(f"{a['nomenclatura']}: licitación de {a['corta']} – {a['entidad_txt']}", 70)
        else:
            titulo = elegir(titulo_aviso(a))
        frases = [f"{a['tipo'] or 'Procedimiento'} {a['nomenclatura']} {de_articulo(a['entidad_txt'])} "
                  f"({a['dep_txt']}).",
                  f"Monto: {a['monto_txt']}." if a["monto_txt"] else "",
                  f"Consultas hasta el {fecha_corta(a['consultas_fin'])}." if a["dias"] is not None and a["dias"] >= 0 else "",
                  cortar(a["descripcion_txt"], 120)]
        escribir(a["path"], "aviso.html", not a["cerrado"], a["lastmod"] if not a["cerrado"] else None,
                 titulo=titulo, h1=h1, descripcion=armar(frases), a=a, migas=migas,
                 misma_entidad=[x for x in sitio.por_entidad.get(a["entidad_slug"], []) if x["ocid"] != a["ocid"]][:5],
                 similares=sitio.similares(a),
                 ld=[x for x in ((sitio.demanda(a) if not a["cerrado"] else None), sitio.breadcrumbs(migas)) if x])

    # Objeto
    for o in objetos:
        avisos = sitio.por_objeto.get(o["nombre"], [])
        r = sitio.resumen(avisos)
        listado(o["path"], avisos, len(avisos) > 0,
                elegir(f"{o['titulo']} del Estado {sitio.anio}: {plural(r['n'], 'vigente', 'vigentes')}",
                       f"{o['titulo']} del Estado {sitio.anio}"),
                f"{o['titulo']} del Estado {sitio.anio}",
                armar([f"{plural(r['n'], 'convocatoria vigente', 'convocatorias vigentes')}.", o["intro"],
                       f"Actualizado el {hoy_txt}."]),
                [("Inicio", "/"), (o["titulo"], None)], intro=o["intro"], extra={"tipo": "objeto"})

    # Rubro
    for rb in rubros:
        avisos = sitio.por_rubro[rb["slug"]]
        r = sitio.resumen(avisos)
        listado(rb["path"], avisos, len(avisos) >= UMBRAL_RUBRO,
                elegir(f"Licitaciones de {rb['nombre'].lower()} {sitio.anio}: {plural(r['n'], 'vigente', 'vigentes')}",
                       f"Licitaciones de {rb['nombre'].lower()} {sitio.anio}"),
                f"Licitaciones de {rb['nombre'].lower()}",
                armar([f"{plural(r['n'], 'licitación vigente', 'licitaciones vigentes')} del Estado peruano en "
                       f"{rb['nombre'].lower()}.", "Clasificadas con los códigos UNSPSC de cada ítem.",
                       f"Actualizado el {hoy_txt}."]),
                [("Inicio", "/"), (rb["nombre"], None)],
                intro="Agrupadas por el código de catálogo (UNSPSC) que la entidad le puso a cada ítem.",
                extra={"tipo": "rubro"})

    # Departamento
    for d in departamentos:
        avisos = sitio.por_dep[d["slug"]]
        r = sitio.resumen(avisos)
        listado(d["path"], avisos, True,
                elegir(f"Licitaciones en {d['nombre']} {sitio.anio}: {plural(r['n'], 'vigente', 'vigentes')}",
                       f"Licitaciones en {d['nombre']} {sitio.anio}"),
                f"Licitaciones del Estado en {d['nombre']}",
                armar([f"{plural(r['n'], 'licitación vigente', 'licitaciones vigentes')} de entidades públicas "
                       f"de {d['nombre']}" + (f", por un total publicado de {r['suma_txt']}." if r["suma_txt"] else "."),
                       f"{plural(r['semana'], 'cierra', 'cierran')} consultas esta semana." if r["semana"] else "",
                       f"Actualizado el {hoy_txt}."]),
                [("Inicio", "/"), (d["nombre"], None)],
                intro=f"Convocadas por entidades con sede en {d['nombre']}. El lugar de ejecución puede ser otro: "
                      "revisa la descripción de cada una.",
                extra={"tipo": "departamento"})

    # Entidad
    for s, avisos in sitio.por_entidad.items():
        nombre = avisos[0]["entidad_txt"]
        r = sitio.resumen(avisos)
        dep = avisos[0]
        listado(f"/entidad/{s}/", avisos, sitio.entidad_indexable[s],
                elegir(f"Licitaciones de {nombre} {sitio.anio}", f"Licitaciones {nombre}"),
                f"Licitaciones {de_articulo(nombre)}",
                armar([f"{plural(r['n'], 'licitación vigente', 'licitaciones vigentes')} {de_articulo(nombre)} "
                       f"({dep['dep_txt']}).", f"Monto publicado: {r['suma_txt']}." if r["suma_txt"] else "",
                       f"Actualizado el {hoy_txt}."]),
                [("Inicio", "/"), (dep["dep_txt"], f"/departamento/{dep['dep_slug']}/"), (nombre, None)],
                extra={"tipo": "entidad"})

    # Rango de monto (solo avisos con monto publicado)
    for rg in rangos:
        avisos = sitio.por_rango.get(rg["slug"], [])
        listado(rg["path"], avisos, len(avisos) > 0,
                elegir(f"Licitaciones del Estado de {rg['nombre'].lower()} ({sitio.anio})"),
                f"Licitaciones {rg['nombre'].lower()}",
                armar([f"{plural(len(avisos), 'licitación vigente', 'licitaciones vigentes')} con monto "
                       f"{rg['nombre'].lower()}.", "Solo las que publican su monto: muchas no lo hacen.",
                       f"Actualizado el {hoy_txt}."]),
                [("Inicio", "/"), (rg["nombre"], None)],
                intro="Solo aparecen las licitaciones que publican su monto en los datos abiertos; "
                      "muchas de bienes y servicios no lo hacen.",
                extra={"tipo": "monto"})

    # Esta semana
    listado("/esta-semana/", semana, True,
            con_marca(f"Licitaciones que cierran consultas esta semana ({hoy_txt})"),
            "Cierran consultas esta semana",
            armar([f"{plural(len(semana), 'licitación', 'licitaciones')} del Estado cuyo plazo de consultas "
                   "termina en los próximos 7 días.", "Ordenadas por fecha límite."]),
            [("Inicio", "/"), ("Esta semana", None)],
            intro="El plazo de consultas es la primera fecha límite del procedimiento: después vienen la "
                  "integración de bases y la presentación de ofertas. Esas fechas no vienen en los datos "
                  "abiertos; están en el cronograma de cada ficha.",
            extra={"tipo": "semana"})

    # Páginas informativas
    for p in INFO:
        escribir(f"/{p['slug']}/", f"info/{p['slug']}.html", p["indexable"], p["lastmod"],
                 titulo=p["title"], h1=p["h1"], descripcion=p["desc"],
                 migas=[("Inicio", "/"), (p["h1"], None)], ld=[])

    # 404 (GitHub Pages la sirve desde la raíz del proyecto)
    html = env.get_template("404.html").render(path="/404.html", canonical=sitio.abs("/404.html"), indexable=False,
                                               titulo="Página no encontrada", h1="Esta página no existe o ya cerró",
                                               descripcion="", ld=[])
    (out / "404.html").write_text(html, encoding="utf-8")

    static = HERE / "static"
    for f in static.rglob("*"):
        if f.is_file() and f.name != "estilos.css":
            dest = out / f.relative_to(static)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    escribir_sitemaps(sitio, out)


def escribir_sitemaps(sitio: Sitio, out: Path) -> None:
    def urlset(paginas):
        filas = []
        for p in paginas:
            lm = f"<lastmod>{p['lastmod']}</lastmod>" if p.get("lastmod") else ""
            filas.append(f"<url><loc>{sitio.abs(p['path'])}</loc>{lm}</url>")
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                + "".join(filas) + "</urlset>\n")

    indexables = [p for p in sitio.paginas if p["indexable"] and "/pagina/" not in p["path"]]
    avisos = [p for p in indexables if p["plantilla"] == "aviso.html"]
    info = [p for p in indexables if p["plantilla"].startswith("info/")]
    listados = [p for p in indexables if p not in avisos and p not in info]
    archivos = []

    def guardar(nombre, grupo):
        (out / nombre).write_text(urlset(grupo), encoding="utf-8")
        archivos.append((nombre, max((p["lastmod"] for p in grupo if p.get("lastmod")), default=None)))

    for i in range(0, max(1, len(avisos)), 2000):
        guardar(f"sitemap-avisos-{i // 2000 + 1}.xml", avisos[i:i + 2000])
    guardar("sitemap-listados.xml", listados)
    guardar("sitemap-info.xml", info)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<sitemap><loc>{sitio.abs('/' + a)}</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "")
                  + "</sitemap>" for a, lm in archivos)
        + "</sitemapindex>\n", encoding="utf-8")
    if not sitio.base_path:
        (out / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\n\nSitemap: {sitio.abs('/sitemap.xml')}\n", encoding="utf-8")


def verificar(sitio: Sitio, out: Path) -> list[str]:
    """Comprobaciones sobre el sitio generado (las mismas de Chamba)."""
    problemas = []
    prohibidas = ["descubre", "sumérgete", "en un solo lugar", "experiencia única", "—"]
    titulos = Counter()
    for f in out.rglob("*.html"):
        html = f.read_text(encoding="utf-8")
        if '"@type":"JobPosting"' in html:
            problemas.append(f"JobPosting en {f}: este sitio no publica empleos")
        if 'content="noindex' in html and '"@type":"Demand"' in html:
            problemas.append(f"Datos estructurados en una página noindex: {f}")
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        if t and 'content="index' in html:
            titulos[t.group(1)] += 1
        texto = re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)).lower()
        for p in prohibidas:
            if p in texto:
                problemas.append(f"Frase prohibida '{p}' en {f.relative_to(out)}")
    dup = [t for t, n in titulos.items() if n > 1]
    if dup:
        print(f"aviso: {len(dup)} títulos repetidos entre páginas indexables (ej.: {dup[0][:80]})")
    return problemas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", default=None, help="state.json (por defecto, junto a --data)")
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--hoy", help="fecha de construcción AAAA-MM-DD (pruebas)")
    args = ap.parse_args(argv)

    data = cargar_json(Path(args.data), {})
    state_path = Path(args.state) if args.state else Path(args.data).with_name("state.json")
    state = cargar_json(state_path, {})
    ahora = datetime.now(LIMA)
    hoy = date.fromisoformat(args.hoy) if args.hoy else ahora.date()

    sitio = Sitio(data, state, args.base_url, hoy, ahora)

    previas = state.get("vigentes_ultima_publicacion") or 0
    if previas and len(sitio.vigentes) < previas * MIN_PROPORCION:
        print(f"ABORTADO: solo {len(sitio.vigentes)} avisos vigentes frente a {previas} de la publicación "
              "anterior. Se conserva el sitio publicado.", file=sys.stderr)
        return 2
    if not sitio.vigentes:
        print("ABORTADO: no hay avisos vigentes.", file=sys.stderr)
        return 2

    construir(sitio, Path(args.out))
    problemas = verificar(sitio, Path(args.out))
    for e in sitio.errores[:20]:
        print("aviso:", e)
    if problemas:
        for p in problemas[:30]:
            print("ERROR:", p, file=sys.stderr)
        return 1

    state["vigentes_ultima_publicacion"] = len(sitio.vigentes)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_idx = sum(1 for p in sitio.paginas if p["indexable"])
    print(f"{len(sitio.vigentes)} avisos vigentes ({len(sitio.abiertos)} con consultas abiertas) · "
          f"{len(sitio.cerrados)} cerrados · {sitio.excluidos} excluidos (convenios/directas) · "
          f"{len(sitio.paginas)} páginas ({n_idx} indexables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
