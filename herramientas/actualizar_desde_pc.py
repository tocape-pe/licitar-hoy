"""Descarga las licitaciones desde esta PC y publica el sitio.

La API del OECE responde 403 a las IP de GitHub Actions (probado el
29-oct-2026), pero no a una conexión de casa. Esta tarea (programada en
Windows con instalar_tarea.ps1) descarga aquí, sube avisos.json a la rama
"data" y lanza el workflow en modo "solo publicar", que genera el sitio con
esos datos. Es la misma receta de Chamba al Toque.

    .venv/Scripts/python herramientas/actualizar_desde_pc.py [--log]

No toca la carpeta de trabajo: el commit en "data" se arma con comandos de
bajo nivel de git sobre el último commit remoto.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRABAJO = REPO / "out" / "pc"
MIN_PROPORCION = 0.5  # igual que build.py: si llega menos de la mitad, algo falló
# Corre con pythonw desde el Programador de tareas: sin esto, cada git/gh abre una consola.
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def git(*args: str, entrada: bytes | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, input=entrada, capture_output=True, check=True,
                       creationflags=SIN_VENTANA)
    return r.stdout.decode("utf-8").strip()


def hay_rama_data() -> bool:
    return bool(git("ls-remote", "--heads", "origin", "data"))


def workflow_en_curso() -> bool:
    r = subprocess.run(["gh", "run", "list", "--workflow", "actualizar.yml", "--limit", "5",
                        "--json", "status", "-q", '[.[] | select(.status != "completed")] | length'],
                       cwd=REPO, capture_output=True, text=True, check=True, creationflags=SIN_VENTANA)
    return r.stdout.strip() not in ("", "0")


def subir_a_data(archivo: Path, mensaje: str) -> str:
    """Reemplaza avisos.json en la rama data conservando state.json."""
    padre, filas = None, []
    if hay_rama_data():
        git("fetch", "-q", "origin", "data")
        padre = git("rev-parse", "origin/data")
        filas = [f for f in git("ls-tree", padre).splitlines() if not f.endswith("\tavisos.json")]
    blob = git("hash-object", "-w", str(archivo))
    filas.append(f"100644 blob {blob}\tavisos.json")
    arbol = git("mktree", entrada=("\n".join(filas) + "\n").encode("utf-8"))
    commit = git("commit-tree", arbol, *(["-p", padre] if padre else []), "-m", mensaje)
    git("push", "-q", "origin", f"{commit}:refs/heads/data")
    return commit


def main() -> int:
    TRABAJO.mkdir(parents=True, exist_ok=True)
    anterior, nuevo = TRABAJO / "previous.json", TRABAJO / "avisos.json"
    salida = None
    if "--log" in sys.argv:  # la tarea programada escribe aquí (pythonw no tiene consola)
        salida = open(TRABAJO / "actualizar.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = salida

    if hay_rama_data():
        git("fetch", "-q", "origin", "data")
        anterior.write_text(git("show", "origin/data:avisos.json"), encoding="utf-8")
    else:
        anterior.write_text("{}", encoding="utf-8")
    n_antes = len(json.loads(anterior.read_text(encoding="utf-8")).get("avisos", []))
    log(f"Datos anteriores: {n_antes} avisos. Descargando del OECE…")

    r = subprocess.run([sys.executable, "-m", "scraper", "--previous", str(anterior),
                        "--output", str(nuevo)], cwd=REPO, stdout=salida, stderr=salida,
                       creationflags=SIN_VENTANA)
    if r.returncode != 0 or not nuevo.exists():
        log("El scraper terminó con error: no se publica nada.")
        return 1
    datos = json.loads(nuevo.read_text(encoding="utf-8"))
    n_ahora, fuente = len(datos["avisos"]), datos["source"]
    if not fuente.get("ok"):
        log(f"Corrida incompleta ({fuente.get('error')}): no se publica.")
        return 1
    if n_antes and n_ahora < n_antes * MIN_PROPORCION:
        log(f"Llegaron {n_ahora} avisos frente a {n_antes}: parece un error, no se publica.")
        return 1

    if workflow_en_curso():
        log("Hay una publicación en curso; se reintenta en la próxima ejecución.")
        return 1
    try:
        commit = subir_a_data(nuevo, f"Avisos desde PC {datetime.now():%Y-%m-%d %H:%M}")
    except subprocess.CalledProcessError:
        log("La rama data cambió mientras tanto; se reintenta una vez.")
        commit = subir_a_data(nuevo, f"Avisos desde PC {datetime.now():%Y-%m-%d %H:%M}")
    log(f"Subido a la rama data ({commit[:7]}): {n_ahora} avisos, {fuente['requests']} peticiones, "
        f"{fuente['seconds'] // 60} min.")

    subprocess.run(["gh", "workflow", "run", "actualizar.yml", "-f", "solo_publicar=true"],
                   cwd=REPO, check=True, capture_output=True, creationflags=SIN_VENTANA)
    log("Publicación lanzada en GitHub Actions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
