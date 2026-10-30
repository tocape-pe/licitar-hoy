import json
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build as B  # noqa: E402
import textos as T  # noqa: E402
from scraper.oece import normalizar  # noqa: E402

CASOS = {r["ocid"].rsplit("-", 1)[1]: r
         for r in json.loads((HERE.parent / "scraper/tests/fixtures/casos.json").read_text(encoding="utf-8"))}
HOY = date(2026, 10, 29)


def sitio(avisos, state=None, hoy=HOY):
    return B.Sitio({"avisos": avisos, "generatedAt": "2026-10-29T11:00:00-05:00"}, {} if state is None else state,
                   "https://licitarhoy.toca.pe", hoy, datetime(2026, 10, 29, 11))


def test_limpiar_signo_huerfano():
    assert T.limpiar("ADQUISICIÓN DE ¿LECHE EVAPORADA¿ Y AVENA") == "ADQUISICIÓN DE LECHE EVAPORADA Y AVENA"
    assert T.limpiar("¿CUÁL ES EL PLAZO?") == "¿CUÁL ES EL PLAZO?"


def test_descripcion_corta_quita_arranques():
    assert T.descripcion_corta("CONTRATACIÓN PARA LA EJECUCIÓN DE LA OBRA: CREACIÓN DE PISTAS") == "creación de pistas"
    assert T.descripcion_corta('DENOMINADA: "CONSTRUCCIÓN DE TRIBUNA') == "construcción de tribuna"
    corta = T.descripcion_corta("ADQUISICION DE MOBILIARIO ESCOLAR PARA LAS INSTITUCIONES EDUCATIVAS DE LA PROVINCIA DE")
    assert len(corta) <= 60 and not corta.endswith(" de")


def test_lugares_con_mayuscula():
    t = T.capitalizar_lugares(T.oracion("OBRA EN EL DISTRITO DE CHALLHUAHUACHO, PROVINCIA DE COTABAMBAS CÓDIGO 1"))
    assert "distrito de Challhuahuacho" in t and "provincia de Cotabambas código" in t


def test_rubros_por_unspsc():
    assert T.rubros(["15101505"]) == ["combustibles"]
    assert T.rubros(["81111500"]) == ["tecnologia-y-software"]  # 8111 es TI, no ingeniería
    assert T.rubros(["81101500"]) == ["ingenieria-y-supervision"]
    assert T.rubros([None]) == []


def test_aviso_vigente_y_titulo():
    s = sitio([normalizar(CASOS["1261357"])])
    a = s.vigentes[0]
    assert a["path"].startswith("/licitacion/") and a["path"].endswith("-1261357/")
    assert a["monto_txt"] == "S/ 222,571.36"
    assert a["rango"] == "100-mil-a-500-mil"
    assert a["dias"] == 4 and a["consultas_txt"] == "Consultas hasta el lunes 2 de noviembre"
    t = B.titulo_aviso(a)
    assert t.startswith("Licitación de mejoramiento") and len(t) <= 70


def test_slug_congelado():
    state = {}
    sitio([normalizar(CASOS["1261357"])], state)
    slug = state["avisos"]["ocds-dgv273-seacev3-1261357"]["slug"]
    cambiado = normalizar(CASOS["1261357"]) | {"descripcion": "OTRA DESCRIPCIÓN COMPLETAMENTE DISTINTA"}
    s = sitio([cambiado], state)
    assert s.vigentes[0]["slug"] == slug


def test_cerrados_y_excluidos():
    desierto = normalizar(CASOS["1259973"])
    convenio = normalizar(CASOS["1261357"]) | {"ocid": "x-1", "tipo": "Convenio"}
    s = sitio([desierto, convenio, normalizar(CASOS["1261357"])])
    assert [a["ocid"] for a in s.cerrados] == [desierto["ocid"]]
    assert s.excluidos == 1


def test_demand_honesto():
    s = sitio([normalizar(CASOS["1261357"]), normalizar(CASOS["1261562"])])
    por = {a["ocid"][-7:]: a for a in s.vigentes}
    ld = s.demanda(por["1261357"])
    assert ld["@type"] == "Demand" and ld["identifier"] == "LP-ABR-7-2026-MDSL/CS-1"
    assert ld["priceSpecification"]["price"] == 222571.36
    assert "priceSpecification" not in s.demanda(por["1261562"])  # sin monto: no se inventa


def test_de_articulo():
    assert B.de_articulo("Instituto de Investigaciones") == "del Instituto de Investigaciones"
    assert B.de_articulo("Municipalidad Distrital de X") == "de la Municipalidad Distrital de X"


def test_salvaguarda_no_publica_si_caen_los_datos(tmp_path):
    data = tmp_path / "avisos.json"
    data.write_text(json.dumps({"avisos": [normalizar(CASOS["1261357"])]}), encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"vigentes_ultima_publicacion": 100}), encoding="utf-8")
    assert B.main(["--data", str(data), "--out", str(tmp_path / "public"), "--hoy", "2026-10-29"]) == 2
    assert not (tmp_path / "public").exists()


def test_construye_sitio_completo(tmp_path):
    data = tmp_path / "avisos.json"
    avisos = [normalizar(r) for r in CASOS.values()]
    # Una licitación ya adjudicada (el caso real 1261494 es contratación directa, que se excluye)
    ganada = {**normalizar(CASOS["1261641"]), "ocid": "ocds-dgv273-seacev3-9999999", "id": "9999999",
              "nomenclatura": "CP-ABR-99-2026-PRUEBA-1", "estado": "ADJUDICADO",
              "adjudicaciones": [{"proveedor": "EMPRESA DE PRUEBA SAC", "ruc": "20123456789",
                                  "monto": 50000.0, "fecha": "2026-10-28"}]}
    data.write_text(json.dumps({"avisos": avisos + [ganada]}), encoding="utf-8")
    assert B.main(["--data", str(data), "--out", str(tmp_path / "public"), "--hoy", "2026-10-29"]) == 0
    pub = tmp_path / "public"
    assert (pub / "sitemap.xml").exists() and (pub / "robots.txt").exists()
    html = next((pub / "licitacion").glob("*1261357/index.html")).read_text(encoding="utf-8")
    assert '"@type":"Demand"' in html and 'content="index' in html
    assert "contratacionesabiertas.oece.gob.pe/proceso/ocds-dgv273-seacev3-1261357" in html
    cerrado = next((pub / "licitacion").glob("*1259973/index.html")).read_text(encoding="utf-8")
    assert 'content="noindex' in cerrado and '"@type":"Demand"' not in cerrado
    adjudicado = next((pub / "licitacion").glob("*9999999/index.html")).read_text(encoding="utf-8")
    assert 'content="index' in adjudicado and "Empresa de Prueba" in adjudicado  # "quién ganó" se indexa
    assert '"@type":"Demand"' not in adjudicado
    assert (pub / "adjudicadas" / "index.html").exists() and (pub / "glosario" / "index.html").exists()
    for indice in ("departamento", "rubro", "entidad", "objeto", "monto"):  # las migas no llevan a un 404
        assert (pub / indice / "index.html").exists()
