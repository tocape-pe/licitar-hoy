import copy
import json
from pathlib import Path

from scraper.__main__ import deduplicar, fusionar
from scraper.oece import normalizar, numero_convocatoria, objeto, releases, ultima_version

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


CASOS = {r["ocid"].rsplit("-", 1)[1]: r for r in read("casos.json")}


class FakeClient:
    """Devuelve las páginas guardadas en orden y anota las URLs pedidas."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return self.pages.pop(0) if self.pages else {"releases": [], "links": {}}


def test_paginacion_sigue_next():
    client = FakeClient(read("lote_p1.json"), read("lote_p2.json"))
    rels = list(releases(client, "2026-10-28", "2026-10-28"))
    assert len(rels) == 6
    assert "startDate=2026-10-28" in client.urls[0] and "sourceId=seace_v3" in client.urls[0]
    assert "searchAfter=" in client.urls[1]
    assert len(client.urls) == 3  # la tercera vuelve vacía y corta


def test_max_paginas():
    client = FakeClient(read("lote_p1.json"), read("lote_p2.json"))
    assert len(list(releases(client, "2026-10-28", "2026-10-28", max_paginas=1))) == 3


def test_obra_con_monto():
    a = normalizar(CASOS["1261357"])
    assert a["nomenclatura"] == "LP-ABR-7-2026-MDSL/CS-1"
    assert a["entidad"] == "MUNICIPALIDAD DISTRITAL DE SAN LUIS - LIMA"
    assert a["departamento"] == "LIMA"
    assert a["tipo"] == "Licitación Pública Abreviada"
    assert a["objeto"] == "Obras"
    assert a["monto"] == 222571.36
    assert a["consultas_fin"].startswith("2026-11-02")
    assert a["estado"] == "CONVOCADO"
    assert a["convocatoria_n"] == 1
    assert a["url"] == "https://contratacionesabiertas.oece.gob.pe/proceso/ocds-dgv273-seacev3-1261357"
    assert a["entidad_ruc"] and a["entidad_ruc"].isdigit()


def test_monto_cero_es_vacio():
    a = normalizar(CASOS["1261562"])
    assert a["monto"] is None
    assert a["objeto"] == "Bienes"


def test_desierto():
    assert normalizar(CASOS["1259973"])["estado"] == "DESIERTO"


def test_segunda_convocatoria():
    assert normalizar(CASOS["1261641"])["convocatoria_n"] == 2
    assert numero_convocatoria("LP-ABR-8-2026-MDM-GM-OC-1-1") == 1
    assert numero_convocatoria("SIN NUMERO") is None


def test_consultoria_de_obra_viene_como_servicio():
    a = normalizar(CASOS["1260486"])
    assert CASOS["1260486"]["tender"]["mainProcurementCategory"] == "services"
    assert a["objeto"] == "Consultoría"
    assert objeto("Concurso Público para Consultoría", "services", "x") == "Consultoría"
    assert objeto("Licitación Pública", "works", "OBRA") == "Obras"


def test_contratacion_directa_sin_plazo():
    a = normalizar(CASOS["1261920"])
    assert a["tipo"] == "Contratación Directa"
    assert a["consultas_fin"] is None


def test_adjudicado():
    a = normalizar(CASOS["1261494"])
    assert a["estado"] == "ADJUDICADO"
    assert a["postores"] == 1
    assert a["adjudicaciones"] == [{
        "proveedor": "E.E.S.S. ONERGY SOCIEDAD ANONIMA CERRADA",
        "ruc": "20605141723",
        "monto": 626184.0,
        "fecha": "2026-10-28",
    }]
    assert a["items"][0]["unspsc"] == "15101505"


def test_basura_se_descarta():
    r = copy.deepcopy(CASOS["1261357"])
    r["tender"]["description"] = " - "
    assert normalizar(r) is None
    r = copy.deepcopy(CASOS["1261357"])
    del r["tender"]["procuringEntity"]
    r.pop("buyer", None)
    assert normalizar(r) is None


def test_ultima_version_gana():
    viejo = copy.deepcopy(CASOS["1261357"])
    viejo["date"] = "2026-10-28T10:19:19-05:00"
    viejo["tender"]["items"][0]["statusDetails"] = "VIEJO"
    nuevo = CASOS["1261357"]
    assert ultima_version([nuevo, viejo])[nuevo["ocid"]] is nuevo
    assert ultima_version([viejo, nuevo])[nuevo["ocid"]] is nuevo


def test_relanzado_tras_nulidad_reemplaza_al_anulado():
    # Caso real 27-oct: obra anulada (1261136) y relanzada (1261296) con la misma nomenclatura.
    nulo = normalizar(CASOS["1261357"]) | {"ocid": "a-1", "estado": "NULO", "publicado": "2026-10-27T13:02:00-05:00"}
    vivo = normalizar(CASOS["1261357"]) | {"ocid": "a-2", "estado": "CONVOCADO", "publicado": "2026-10-27T15:23:00-05:00"}
    otra_entidad = normalizar(CASOS["1261357"]) | {"ocid": "b-1", "entidad": "OTRA MUNICIPALIDAD"}
    out = {a["ocid"]: a for a in deduplicar([nulo, vivo, otra_entidad])}
    assert set(out) == {"a-2", "b-1"}
    assert out["a-2"]["reemplaza"] == ["a-1"]
    assert "reemplaza" not in out["b-1"]


def test_fusionar_hereda_visto_y_retiene():
    previo = normalizar(CASOS["1261357"]) | {"visto": "2026-10-20"}
    viejisimo = normalizar(CASOS["1261562"]) | {"visto": "2026-07-01", "publicado": "2026-07-01T10:00:00-05:00"}
    fuera_de_ventana = normalizar(CASOS["1259973"]) | {"visto": "2026-10-01"}
    nuevo = normalizar(CASOS["1261357"])
    nuevo["estado"] = "ADJUDICADO"
    out = fusionar([previo, viejisimo, fuera_de_ventana], [nuevo], "2026-10-29", retener=60)
    por_ocid = {a["ocid"]: a for a in out}
    assert por_ocid[nuevo["ocid"]]["estado"] == "ADJUDICADO"
    assert por_ocid[nuevo["ocid"]]["visto"] == "2026-10-20"
    assert fuera_de_ventana["ocid"] in por_ocid
    assert viejisimo["ocid"] not in por_ocid
