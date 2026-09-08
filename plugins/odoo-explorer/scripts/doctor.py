"""Check that everything odoo-explorer needs is in place.

Written so that someone without a technical background understands what is
missing and what to do about it:

  python3 doctor.py                 # human-readable diagnosis
  python3 doctor.py --json          # the same diagnosis, for Claude
  python3 doctor.py --instalar      # install whatever can install itself
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import odoo_source  # noqa: E402
from odoo_ro import list_instances, project_root  # noqa: E402

ARCHIFY = pathlib.Path.home() / ".claude" / "skills" / "archify"
MIN_LIBRE_GB = 1.5


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout or r.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def revisar(project=None):
    checks = []

    v = sys.version_info
    checks.append({
        "clave": "python",
        "titulo": "Python",
        "ok": v >= (3, 8),
        "detalle": "Python %d.%d.%d" % (v.major, v.minor, v.micro),
        "arreglo": "Instala Python 3.8 o superior desde python.org.",
        "critico": True,
    })

    node = shutil.which("node")
    code, out = _run(["node", "--version"]) if node else (1, "no encontrado")
    mayor = 0
    if code == 0 and out.startswith("v"):
        try:
            mayor = int(out[1:].split(".")[0])
        except ValueError:
            mayor = 0
    checks.append({
        "clave": "node",
        "titulo": "Node.js",
        "ok": mayor >= 18,
        "detalle": out if node else "no esta instalado",
        "arreglo": "Instala Node 18 o superior desde nodejs.org. Sin Node no hay "
                   "diagramas, pero el resto de odoo-explorer sigue funcionando.",
        "critico": False,
    })

    archify_ok = (ARCHIFY / "bin" / "archify.mjs").exists()
    detalle = "instalado en %s" % ARCHIFY if archify_ok else "no instalado"
    if archify_ok and mayor >= 18:
        code, _out = _run(["node", str(ARCHIFY / "bin" / "archify.mjs"), "doctor"])
        if code != 0:
            archify_ok = False
            detalle = "instalado pero su propio diagnostico falla"
    checks.append({
        "clave": "archify",
        "titulo": "Archify (los diagramas)",
        "ok": archify_ok,
        "detalle": detalle,
        "arreglo": "npx skills add tt-a1i/archify -g   (o ejecuta este doctor con --instalar)",
        "critico": False,
        "instalable": True,
    })

    for herramienta, para in (("curl", "descargar el codigo fuente"),
                              ("unzip", "descomprimirlo")):
        checks.append({
            "clave": herramienta,
            "titulo": herramienta,
            "ok": bool(shutil.which(herramienta)),
            "detalle": shutil.which(herramienta) or "no encontrado",
            "arreglo": "Necesario para %s. Instalalo con el gestor de paquetes de tu "
                       "sistema." % para,
            "critico": herramienta == "curl",
        })

    cache = odoo_source.cache_root()
    base = cache if cache.exists() else cache.parent
    while not base.exists() and base != base.parent:
        base = base.parent
    libre_gb = shutil.disk_usage(base).free / 1e9
    checks.append({
        "clave": "disco",
        "titulo": "Espacio en disco",
        "ok": libre_gb >= MIN_LIBRE_GB,
        "detalle": "%.1f GB libres en %s" % (libre_gb, base),
        "arreglo": "Cada version de Odoo ocupa ~1,2 GB descomprimida. Libera espacio o "
                   "cambia la ruta con la variable ODOO_SRC_CACHE.",
        "critico": False,
    })

    series = []
    if cache.is_dir():
        series = sorted(d.name for d in cache.iterdir()
                        if d.is_dir() and (d / "SOURCE.json").exists())
    checks.append({
        "clave": "fuentes",
        "titulo": "Versiones de Odoo descargadas",
        "ok": True,
        "detalle": ", ".join(series) if series else "ninguna todavia",
        "arreglo": "Se descargan solas al conectar con una instancia.",
        "critico": False,
    })

    inst = list_instances(project)
    checks.append({
        "clave": "instancias",
        "titulo": "Instancias dadas de alta",
        "ok": True,
        "detalle": ", ".join(inst) if inst else "ninguna todavia",
        "arreglo": "Da de alta la primera con /odoo-connect.",
        "critico": False,
    })

    faltan_criticos = [c for c in checks if c["critico"] and not c["ok"]]
    faltan_otros = [c for c in checks if not c["critico"] and not c["ok"]
                    and c["clave"] not in ("fuentes", "instancias")]
    return {
        "proyecto": str(project_root(project)),
        "checks": checks,
        "listo": not faltan_criticos,
        "diagramas_disponibles": all(
            c["ok"] for c in checks if c["clave"] in ("node", "archify")),
        "pendientes": [c["clave"] for c in faltan_criticos + faltan_otros],
    }


def instalar_archify():
    if not shutil.which("npx"):
        return False, "npx no esta disponible: instala Node.js primero."
    code, out = _run(["npx", "-y", "skills", "add", "tt-a1i/archify",
                      "--skill", "archify", "--agent", "claude-code",
                      "--global", "--copy", "--yes"])
    return code == 0, out[-800:]


def imprimir(rep):
    print()
    print("  Diagnostico de odoo-explorer")
    print("  " + "-" * 44)
    for c in rep["checks"]:
        marca = "OK " if c["ok"] else ("!! " if c["critico"] else " * ")
        print("  %s %-32s %s" % (marca, c["titulo"], c["detalle"]))
    print("  " + "-" * 44)
    if rep["listo"] and rep["diagramas_disponibles"]:
        print("  Todo listo. Puedes conectar una instancia con /odoo-connect.")
    elif rep["listo"]:
        print("  Puedes trabajar, pero sin diagramas: falta Node o Archify.")
        print("  El dossier se genera igual y deja los diagramas como pendientes.")
    else:
        print("  Falta algo imprescindible:")
    for c in rep["checks"]:
        if not c["ok"] and c["clave"] not in ("fuentes", "instancias"):
            print()
            print("  %s: %s" % (c["titulo"], c["arreglo"]))
    print()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project")
    p.add_argument("--json", action="store_true")
    p.add_argument("--instalar", action="store_true",
                   help="instala Archify si falta (necesita Node y red)")
    a = p.parse_args(argv)

    if a.instalar:
        rep = revisar(a.project)
        arch = next(c for c in rep["checks"] if c["clave"] == "archify")
        if arch["ok"]:
            print("Archify ya esta instalado.")
        else:
            print("Instalando Archify...", file=sys.stderr)
            ok, out = instalar_archify()
            print(("Instalado." if ok else "No se pudo instalar:\n" + out))

    rep = revisar(a.project)
    if a.json:
        json.dump(rep, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        imprimir(rep)
    raise SystemExit(0 if rep["listo"] else 1)


if __name__ == "__main__":
    main()
