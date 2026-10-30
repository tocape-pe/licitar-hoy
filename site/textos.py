"""Convierte los datos del OECE (casi todo en MAYÚSCULAS, textos largos) en
textos legibles: nombres, slugs, descripciones cortas y rubros.

La parte de nombres y slugs viene de Chamba al Toque (site/textos.py).
Todo sale de los campos oficiales; no se inventa nada."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

MINUSCULAS = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "para", "por",
              "con", "a", "al", "sin", "un", "una"}

# Siglas que se dejan en mayúsculas. Solo siglas que no son palabras comunes
# (nada de "MAS", "ANA" o "PRODUCE", que también aparecen como palabras).
SIGLAS = {
    "CAS", "SERVIR", "UGEL", "DRE", "DIRESA", "GERESA", "MINSA", "ESSALUD", "SUNAT", "SUNARP",
    "PNP", "ONP", "INEI", "OCI", "SIS", "RENIEC", "JNE", "ONPE", "SUNAFIL", "OSINERGMIN",
    "OSIPTEL", "SUNASS", "INDECOPI", "MEF", "MTPE", "MINEDU", "MIDIS", "MIMP", "MINAM", "MINEM",
    "MIDAGRI", "MINCETUR", "SENASA", "SENAMHI", "SERNANP", "SUCAMEC", "SUTRAN", "INPE", "INABIF",
    "OEFA", "SBS", "BCRP", "PCM", "MTC", "MVCS", "MINJUSDH", "TI", "TIC", "RRHH", "SST", "SIAF",
    "SIGA", "SEACE", "OSCE", "UNI", "UNMSM", "SAC", "EPS", "SEDAPAL", "EMAPE", "FONCODES",
    "PRONABEC", "DEVIDA", "CENEPRED", "INDECI", "COFOPRI", "ATU", "MML", "SAT", "SATT", "DNI",
    "CTS", "IGV", "ONG", "PNUD", "CEPLAN", "FAP", "CEM", "DEMUNA", "OMAPED", "CIAM", "ULE",
    "AIS", "UTES", "PAD", "EESS", "IPRESS", "SAMU", "PRONIS", "PROVIAS", "SERFOR", "ANA", "AAA",
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
}
# Palabras con mayúscula interna o forma propia.
FORMAS = {"essalud": "EsSalud", "pronied": "Pronied", "proinversion": "ProInversión"}

# La fuente suele venir sin tildes. Palabras frecuentes de cargos y
# entidades; los topónimos van con mayúscula. Se amplía con
# data/correcciones.csv.
TILDES = {
    "tecnico": "técnico", "tecnica": "técnica", "tecnicos": "técnicos", "mecanico": "mecánico",
    "psicologo": "psicólogo", "psicologa": "psicóloga", "psicologia": "psicología",
    "medico": "médico", "medica": "médica", "quimico": "químico", "quimica": "química",
    "biologo": "biólogo", "biologa": "bióloga", "economico": "económico", "economia": "economía",
    "juridico": "jurídico", "juridica": "jurídica", "publico": "público", "publica": "pública",
    "publicos": "públicos", "publicas": "públicas", "logistica": "logística",
    "estadistica": "estadística", "informatica": "informática", "ingenieria": "ingeniería",
    "enfermeria": "enfermería", "auditoria": "auditoría", "tesoreria": "tesorería",
    "contraloria": "contraloría", "procuraduria": "procuraduría", "policia": "policía",
    "odontologia": "odontología", "odontologo": "odontólogo", "topografo": "topógrafo",
    "cartografo": "cartógrafo", "geografo": "geógrafo", "agronomo": "agrónomo",
    "electronico": "electrónico", "electrica": "eléctrica", "electrico": "eléctrico",
    "vehiculo": "vehículo", "vehiculos": "vehículos", "maquina": "máquina", "maquinas": "máquinas",
    "albanil": "albañil", "basico": "básico", "basica": "básica", "academico": "académico",
    "academica": "académica", "pedagogico": "pedagógico", "pedagogica": "pedagógica",
    "pedagogia": "pedagogía", "tecnologia": "tecnología", "metodologia": "metodología",
    "energia": "energía", "mineria": "minería", "almacen": "almacén", "region": "región",
    "credito": "crédito", "creditos": "créditos", "tramite": "trámite", "tramites": "trámites",
    "analisis": "análisis", "diagnostico": "diagnóstico", "especifico": "específico",
    "especifica": "específica", "telefonico": "telefónico", "telefonica": "telefónica",
    "camara": "cámara", "unico": "único", "unica": "única", "practicas": "prácticas",
    "pagina": "página", "ambito": "ámbito", "transito": "tránsito", "mas": "más",
    "obstetra": "obstetra", "quirurgico": "quirúrgico", "clinico": "clínico", "clinica": "clínica",
    "radiologia": "radiología", "laboratorio": "laboratorio", "nutricion": "nutrición",
    "computo": "cómputo", "sistematizacion": "sistematización", "chofer": "chofer",
    "guardian": "guardián", "jardineria": "jardinería", "carpinteria": "carpintería",
    "cobranza": "cobranza", "fiscalizacion": "fiscalización", "linea": "línea", "lineas": "líneas",
    "pais": "país", "rio": "río", "vias": "vías", "via": "vía", "dias": "días",
    "matematica": "matemática", "matematicas": "matemáticas", "fisica": "física", "fisico": "físico",
    "musica": "música", "artistico": "artístico", "historico": "histórico", "turistico": "turístico",
    "ecologico": "ecológico", "geologo": "geólogo", "hidraulico": "hidráulico",
    "hidraulica": "hidráulica", "mecanica": "mecánica", "automotriz": "automotriz",
    "estrategico": "estratégico", "estrategica": "estratégica", "politica": "política",
    "politicas": "políticas", "codigo": "código", "deposito": "depósito",
    "gestion": "gestión", "cuestion": "cuestión", "oncologo": "oncólogo", "oncologa": "oncóloga",
    "cardiologo": "cardiólogo", "neurologo": "neurólogo", "ginecologo": "ginecólogo",
    "pediatria": "pediatría", "anestesiologo": "anestesiólogo", "radiologo": "radiólogo",
    "tecnologo": "tecnólogo", "tecnologa": "tecnóloga", "arqueologo": "arqueólogo",
    "sociologo": "sociólogo", "antropologo": "antropólogo", "educacion": "educación",
    "medicos": "médicos", "basicos": "básicos", "tecnicas": "técnicas", "unidad": "unidad",
    "numero": "número", "despues": "después", "telefono": "teléfono", "tactico": "táctico",
    "transito": "tránsito", "rapido": "rápido", "rapida": "rápida", "util": "útil",
    "aerea": "aérea", "aereo": "aéreo", "tecnologico": "tecnológico", "tecnologica": "tecnológica",
    "organico": "orgánico", "patrimonio": "patrimonio", "arqueologico": "arqueológico",
    "geologico": "geológico", "hidrografico": "hidrográfico", "periodico": "periódico",
    # Departamentos y topónimos frecuentes
    "ancash": "Áncash", "apurimac": "Apurímac", "huanuco": "Huánuco", "junin": "Junín",
    "martin": "Martín", "pachacamac": "Pachacámac", "canete": "Cañete", "rimac": "Rímac",
    "peru": "Perú", "jaen": "Jaén", "lurin": "Lurín", "ferrenafe": "Ferreñafe",
    "camana": "Camaná", "huancane": "Huancané", "vilcashuaman": "Vilcashuamán",
    "concepcion": "Concepción", "asuncion": "Asunción", "ascension": "Ascensión",
    "zarate": "Zárate", "nanay": "Nanay", "maranon": "Marañón", "chancay": "Chancay",
    "carhuaz": "Carhuaz", "yungay": "Yungay", "bolivar": "Bolívar", "sucre": "Sucre",
    "paucar": "Páucar", "huamanga": "Huamanga", "andres": "Andrés", "ramon": "Ramón",
    "maria": "María", "jesus": "Jesús", "jose": "José", "tupac": "Túpac", "amaru": "Amaru",
    "angeles": "Ángeles", "lopez": "López", "perez": "Pérez", "gonzalez": "González",
    "garcia": "García", "rodriguez": "Rodríguez", "fernandez": "Fernández", "sanchez": "Sánchez",
    "ramirez": "Ramírez", "martinez": "Martínez", "vasquez": "Vásquez", "gomez": "Gómez",
    "hernandez": "Hernández", "chavez": "Chávez", "jimenez": "Jiménez", "diaz": "Díaz",
    "ruiz": "Ruiz", "alvarez": "Álvarez", "cesar": "César", "victor": "Víctor", "nicolas": "Nicolás",
    "tomas": "Tomás", "simon": "Simón", "agustin": "Agustín", "sebastian": "Sebastián",
    "joaquin": "Joaquín", "ines": "Inés", "belen": "Belén", "jeronimo": "Jerónimo",
    "huancavelica": "Huancavelica", "tumbes": "Tumbes",
}

SIN_DICCIONARIO: Counter = Counter()


def cargar_correcciones(path) -> int:
    """Lee pares 'ORIGINAL,Corrección' (una por línea) y los suma a TILDES."""
    p = Path(path)
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "," not in line:
            continue
        a, b = (x.strip() for x in line.split(",", 1))
        if a and b:
            TILDES[a.lower()] = b
            n += 1
    return n


def _es_sigla(w: str) -> bool:
    bare = w.strip("()[],;:\"'-/")
    if not bare or bare.lower() in MINUSCULAS:  # "Y", "O", "E" no son siglas
        return False
    if bare.upper() in SIGLAS or re.search(r"\d", bare):
        return True
    if "." in bare.strip("."):
        # "R.D.", "S.A.C." sí; "DIREC.REGIONAL" no (son palabras abreviadas).
        return all(len(s) <= 3 for s in bare.split(".") if s)
    # Siglas sin vocales: "PJ", "MPL", "DGPR".
    return len(bare) <= 5 and not re.search(r"[AEIOUÁÉÍÓÚaeiouáéíóú]", bare)


def _acentuar(low: str) -> str:
    """Pone tildes a una palabra en minúsculas, si viene sin ellas. Los
    topónimos del diccionario vuelven con su mayúscula."""
    if re.search(r"[áéíóúñü]", low):
        return low
    m = re.match(r"^([^a-z]*)([a-z]+)([^a-z]*)$", low)
    if not m:
        return low
    pre, core, post = m.groups()
    if core in FORMAS:
        return pre + FORMAS[core] + post
    if core in TILDES:
        return pre + TILDES[core] + post
    if len(core) > 4 and core.endswith("cion"):
        return pre + core[:-4] + "ción" + post
    if len(core) > 4 and core.endswith("sion"):
        return pre + core[:-4] + "sión" + post
    if len(core) > 3:
        SIN_DICCIONARIO[core] += 1
    return low


def _capital(w: str) -> str:
    low = _acentuar(w.lower())
    i = next((k for k, ch in enumerate(low) if ch.isalpha()), None)
    return low if i is None else low[:i] + low[i].upper() + low[i + 1:]


def _palabras(texto: str) -> list[str]:
    return re.sub(r"\s+", " ", texto or "").strip().split(" ")


def _sigla(w: str) -> str:
    bare = w.strip("()[],;:\"'-/").lower()
    return w.replace(w.strip("()[],;:\"'-/"), FORMAS[bare]) if bare in FORMAS else w.upper()


def _titulo_palabra(w: str, primera: bool, prev: str) -> str:
    # Palabras unidas por guion o punto ("PUBLICO-GERENCIA", "DIREC.REGIONAL"):
    # cada parte se trata por separado.
    for sep in ("-", "."):
        if sep in w.strip(sep) and not _es_sigla(w):
            partes = w.split(sep)
            return sep.join(_titulo_palabra(p, primera and k == 0, prev) if p else p
                            for k, p in enumerate(partes))
    bare = w.strip("()[],;:\"'")
    if _es_sigla(w) or bare.lower() in FORMAS:
        return _sigla(w)
    # Sigla corta tras un guion al final de un cargo: "... - ODM".
    if (prev in {"-", "–"} and 2 <= len(bare) <= 4 and bare.isalpha() and bare.lower() not in TILDES
            and len(re.findall(r"[AEIOUaeiou]", bare)) <= 1):
        return w.upper()
    if not primera and w.lower() in MINUSCULAS and not prev.endswith(("-", "(")):
        return w.lower()
    return _capital(w)


def nombre_propio(texto: str) -> str:
    """Formato título: 'MUNICIPALIDAD  DISTRITAL DE PACHACAMAC' ->
    'Municipalidad Distrital de Pachacámac'. Se usa para cargos y entidades."""
    out = []
    prev = ""
    for i, w in enumerate(_palabras(texto)):
        if not w:
            continue
        out.append(_titulo_palabra(w, i == 0, prev))
        prev = w
    return " ".join(out)


def oracion(texto: str) -> str:
    """Formato oración para textos largos: 'LIMPIEZA DE AMBIENTES; DESINFECCIÓN'
    -> 'Limpieza de ambientes; desinfección' (respeta siglas y topónimos)."""
    out = []
    inicio = True  # tras un punto o una viñeta empieza otra oración
    for w in _palabras(texto):
        if not w:
            continue
        if w in {"•", "-", "*"}:
            out.append(w)
            inicio = True
            continue
        if _es_sigla(w) or w.strip("()").lower() in FORMAS:
            out.append(_sigla(w))
        elif inicio or w.startswith("•"):
            out.append(_capital(w))
        else:
            out.append(_acentuar(w.lower()))
        inicio = w.endswith(".") and not _es_sigla(w)
    return " ".join(out)


def normalizar_entidad(texto: str) -> str:
    """'UNIDAD DE GESTION EDUCATIVA LOCAL # 01' -> 'UGEL 01' (así se busca)."""
    t = re.sub(r"\s+", " ", texto or "").strip()
    return re.sub(r"^UNIDAD DE GESTI[OÓ]N EDUCATIVA LOCAL\s*(?:N[°º.]*|#|NRO\.?)?\s*(\d+)",
                  r"UGEL \1", t, flags=re.I)


def slug(texto: str, max_len: int = 80) -> str:
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rsplit("-", 1)[0]
    return s or "oferta"


ABREVIATURAS_SLUG = [
    ("municipalidad-distrital-de-", "muni-distrital-"),
    ("municipalidad-provincial-de-", "muni-provincial-"),
    ("municipalidad-metropolitana-de-", "muni-metropolitana-"),
    ("municipalidad-distrital-", "muni-distrital-"),
    ("municipalidad-provincial-", "muni-provincial-"),
    ("municipalidad-de-", "muni-"),
    ("gobierno-regional-de-", "gore-"),
    ("gobierno-regional-", "gore-"),
    ("unidad-de-gestion-educativa-local-", "ugel-"),
    ("direccion-regional-de-", "dir-regional-"),
    ("universidad-nacional-", "un-"),
    ("ministerio-de-", "min-"),
]


COLGANTES = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "en", "a", "al", "para", "con", "n"}


def _recortar_slug(s: str, maximo: int) -> str:
    partes = s.split("-")
    out = []
    for p in partes:
        if len("-".join(out + [p])) > maximo:
            break
        out.append(p)
    while out and out[-1] in COLGANTES:
        out.pop()
    return "-".join(out)



def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def limpiar(texto: str | None) -> str:
    """Quita el "¿" huérfano que el SEACE deja donde iban comillas o guiones
    ('ADQUISICIÓN DE ¿LECHE EVAPORADA¿', 'LIMA¿ I ETAPA'). Si el texto tiene
    un '?', el '¿' es una pregunta de verdad y se respeta."""
    t = (texto or "").replace("\\n", " ")  # algunos traen el salto de línea escrito como texto
    if "¿" in t and "?" not in t:
        t = t.replace("¿", " ")
    return re.sub(r"\s+", " ", t).strip(" ,;:-")


# Arranques burocráticos que no dicen QUÉ se compra: se quitan para el título.
_ARRANQUE = re.compile(
    r"^(?:(?:LA|EL|DE|DEL|PARA|POR|A|LOS|LAS|EN)\s+|"
    r"(?:CONTRATACION|CONTRATAR|ADQUISICION|ADQUIRIR|REQUERIMIENTO|SOLICITUD|"
    r"PROCEDIMIENTO|SELECCION)\s+|"
    r"(?:EJECUCION|ELABORACION)\s+(?:DE\s+)?(?:LA\s+)?(?:OBRA\s*)?:?\s*|"
    r"OBRA\s*:\s*|DENOMINAD[OA]\s*:?\s*|SOLO\s+|[\"'“”:;.\-]+\s*)")


def descripcion_corta(descripcion: str, maximo: int = 60) -> str:
    """'CONTRATACIÓN PARA LA EJECUCIÓN DE LA OBRA: CREACIÓN DE PISTAS…' ->
    'creación de pistas…' en minúscula inicial, para 'Licitación de …'.
    Corta en una palabra completa, sin dejar 'de'/'y' colgando."""
    t = limpiar(descripcion)
    base = _sin_tildes(t).upper()
    while True:
        m = _ARRANQUE.match(base)
        if not m or not m.group(0):
            break
        t, base = t[m.end():], base[m.end():]
    t = capitalizar_lugares(oracion(re.sub(r'["“”]', "", t).strip())) or oracion(limpiar(descripcion))
    if len(t) > maximo:
        palabras = t[:maximo + 1].split(" ")[:-1]
        while palabras and palabras[-1].lower().strip(",;:") in COLGANTES:
            palabras.pop()
        t = " ".join(palabras).rstrip(",;:(")
    # minúscula inicial salvo siglas o nombres propios ("UGEL", "Cusco")
    primera = t.split(" ", 1)[0] if t else ""
    if primera and not _es_sigla(primera) and primera[:1].isupper() and primera[1:2].islower():
        bare = re.sub(r"\W", "", primera).lower()
        if bare not in TILDES or TILDES[bare][:1].islower():
            t = t[:1].lower() + t[1:]
    return t


def slug_aviso(corta: str, entidad: str, id_: str) -> str:
    """'{qué}-{entidad corta}-{id}': lo mismo que slug_oferta de Chamba."""
    c = _recortar_slug(slug(corta, 200), 45) or "licitacion"
    e = slug(normalizar_entidad(entidad), 200) + "-"
    for largo, corto in ABREVIATURAS_SLUG:
        if e.startswith(largo):
            e = corto + e[len(largo):]
            break
    e = _recortar_slug(e.strip("-"), max(10, 70 - len(c) - 1))
    return "-".join(x for x in (c, e, id_) if x)


# Rubros en palabras de pyme, armados con los códigos UNSPSC oficiales de cada
# ítem (segmento de 2 dígitos o familia de 4). Un aviso puede caer en varios.
RUBROS = [
    {"slug": "construccion-y-obras", "nombre": "Construcción y obras", "codigos": ["72"]},
    {"slug": "materiales-de-construccion", "nombre": "Materiales de construcción", "codigos": ["30", "40"]},
    {"slug": "ingenieria-y-supervision", "nombre": "Ingeniería, estudios y supervisión", "codigos": ["81"],
     "excluir": ["8111", "8112", "8116"]},
    {"slug": "tecnologia-y-software", "nombre": "Tecnología, software y redes",
     "codigos": ["43", "8111", "8112", "8116"]},
    {"slug": "combustibles", "nombre": "Combustibles", "codigos": ["15"]},
    {"slug": "alimentos", "nombre": "Alimentos y comedores", "codigos": ["50", "9014", "9015"]},
    {"slug": "salud-y-medicinas", "nombre": "Salud, medicinas y equipo médico", "codigos": ["41", "42", "51", "85"]},
    {"slug": "vehiculos-y-maquinaria", "nombre": "Vehículos y maquinaria", "codigos": ["25", "22", "21", "24", "27"]},
    {"slug": "transporte-y-mecanica", "nombre": "Transporte y mecánica", "codigos": ["78"]},
    {"slug": "seguridad-y-vigilancia", "nombre": "Seguridad y vigilancia", "codigos": ["92", "46"]},
    {"slug": "limpieza-y-residuos", "nombre": "Limpieza y residuos", "codigos": ["76", "47"]},
    {"slug": "consultoria-y-gestion", "nombre": "Consultoría, capacitación y gestión",
     "codigos": ["80", "84", "86", "93", "77"]},
    {"slug": "uniformes-y-textiles", "nombre": "Uniformes, ropa y calzado", "codigos": ["53"]},
    {"slug": "mobiliario-y-oficina", "nombre": "Mobiliario, oficina e imprenta", "codigos": ["56", "44", "14", "55", "82"]},
    {"slug": "agro-y-ganaderia", "nombre": "Agro, ganadería y riego", "codigos": ["10", "70"]},
    {"slug": "electricidad-y-energia", "nombre": "Electricidad y energía", "codigos": ["26", "39"]},
]


def rubros(codigos_unspsc: list[str]) -> list[str]:
    """Slugs de rubro para los códigos UNSPSC de los ítems de un aviso."""
    out = []
    for r in RUBROS:
        for c in codigos_unspsc:
            c = c or ""
            if (any(c.startswith(p) for p in r["codigos"])
                    and not any(c.startswith(x) for x in r.get("excluir", []))):
                out.append(r["slug"])
                break
    return out


# Palabras frecuentes en descripciones de compras públicas que la fuente trae sin tilde.
TILDES.update({
    "consultoria": "consultoría", "electricas": "eléctricas", "electricos": "eléctricos",
    "electronicos": "electrónicos", "electronica": "electrónica", "areas": "áreas", "area": "área",
    "asfaltico": "asfáltico", "asfaltica": "asfáltica", "farmaceutico": "farmacéutico",
    "farmaceuticos": "farmacéuticos", "farmaceutica": "farmacéutica", "farmaceuticas": "farmacéuticas",
    "hemodialisis": "hemodiálisis", "camaras": "cámaras", "ferreteria": "ferretería",
    "hidrico": "hídrico", "hidricos": "hídricos", "hidrica": "hídrica", "agricola": "agrícola",
    "agricolas": "agrícolas", "metalica": "metálica", "metalicas": "metálicas", "metalico": "metálico",
    "metalicos": "metálicos", "plastico": "plástico", "plasticos": "plásticos", "logistico": "logístico",
    "petroleo": "petróleo", "kilometro": "kilómetro", "kilometros": "kilómetros",
    "topografico": "topográfico", "geotecnico": "geotécnico", "mecanicos": "mecánicos",
    "quimicos": "químicos", "termico": "térmico", "acustico": "acústico", "critico": "crítico",
    "practico": "práctico", "tecnologicos": "tecnológicos", "academicos": "académicos",
    "medicas": "médicas", "quirurgicos": "quirúrgicos", "odontologicos": "odontológicos",
    "biomedico": "biomédico", "biomedicos": "biomédicos", "basicas": "básicas", "economicos": "económicos",
    "vehicular": "vehicular", "urbanizacion": "urbanización", "almacenes": "almacenes",
    "cubiculos": "cubículos", "modulo": "módulo", "modulos": "módulos", "ultimo": "último",
    "multiple": "múltiple", "multiples": "múltiples", "cientifico": "científico", "periferico": "periférico",
    "perifericos": "periféricos", "informaticos": "informáticos", "informaticas": "informáticas",
    "deportivo": "deportivo", "estadio": "estadio", "vias": "vías", "caminos": "caminos",
    "jiron": "jirón", "pasaje": "pasaje", "avenida": "avenida", "puente": "puente",
    "oxigeno": "oxígeno", "liquido": "líquido", "liquidos": "líquidos", "solido": "sólido",
    "solidos": "sólidos", "organicos": "orgánicos", "toxico": "tóxico", "toxicos": "tóxicos",
})


# Tras estas palabras viene un nombre de lugar, que la fuente trae en mayúsculas
# y oracion() deja en minúscula: "distrito de challhuahuacho" -> "distrito de Challhuahuacho".
_LUGAR = re.compile(
    r"\b((?:distrito|provincia|departamento|regi[oó]n|localidad|caser[ií]o|centro poblado|c\.\s?p\.|"
    r"comunidad(?:es)?(?: campesinas?| nativas?)?|anexos?|sector(?:es)?|urbanizaci[oó]n|asentamiento humano|barrio|"
    r"municipalidad(?: distrital| provincial)?|ciudad|r[ií]o|quebrada|laguna|cerro)"
    r"(?:\s+(?:de|del|la|los|las))*\s+)((?:[a-záéíóúñü][\wáéíóúñü.'-]*)(?:\s+[a-záéíóúñü][\wáéíóúñü.'-]*){0,3})")


def capitalizar_lugares(texto: str) -> str:
    def nombre(m):
        palabras = m.group(2).split(" ")
        out = []
        for w in palabras:
            bare = re.sub(r"[^\wáéíóúñü]", "", w)
            comun = TILDES.get(_sin_tildes(bare), "")[:1].islower() or bare in TILDES.values()
            if w in MINUSCULAS or comun or bare in {"provincia", "distrito", "departamento", "region", "región"}:
                break
            out.append(_capital(w))
        resto = palabras[len(out):]
        return m.group(1) + " ".join(out + resto)
    return _LUGAR.sub(nombre, texto)
