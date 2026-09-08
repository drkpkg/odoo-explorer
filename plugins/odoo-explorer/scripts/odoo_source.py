"""Cache local del codigo fuente de Odoo por serie.

La instancia dice QUE hay configurado; el codigo fuente dice COMO funciona el
proceso (maquina de estados, que hace cada boton, que registros crea). Sin la
fuente, un dossier de proceso es adivinanza.

  python3 odoo_source.py ensure 18.0          # descarga+descomprime si no esta
  python3 odoo_source.py path 18.0            # ruta y directorios de addons
  python3 odoo_source.py list                 # series ya cacheadas
  python3 odoo_source.py find-model mrp.production --serie 18.0
  python3 odoo_source.py grep "def action_confirm" --serie 18.0 --modules mrp
  python3 odoo_source.py module mrp --serie 18.0

Cache por defecto: ~/.cache/odoo-src/<serie>/   (override: ODOO_SRC_CACHE)
Fuente: https://nightly.odoo.com/<serie>/nightly/src/odoo_<serie>.latest.zip
"""
import argparse
import ast
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

NIGHTLY = "https://nightly.odoo.com/{serie}/nightly/src/odoo_{serie}.latest.zip"
GITHUB_FALLBACK = "https://github.com/odoo/odoo/archive/refs/heads/{serie}.zip"


def cache_root():
    env = os.environ.get("ODOO_SRC_CACHE")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    return pathlib.Path.home() / ".cache" / "odoo-src"


def normalize_serie(serie):
    """'18.0+e' -> '18.0'. 'saas~18.1' -> '18.0' con aviso."""
    serie = str(serie).strip()
    warn = None
    raw = serie
    serie = serie.split("+")[0]
    m = re.match(r"^saas[-~](\d+)\.(\d+)$", serie)
    if m:
        serie = "%s.0" % m.group(1)
        warn = ("La instancia declara %r (Odoo Online / saas). El nightly publico "
                "no publica esa serie: se usa la fuente de %s, que es la base. "
                "Puede haber diferencias en modulos saas." % (raw, serie))
    if not re.match(r"^\d+\.\d+$", serie) and serie != "master":
        raise SystemExit("Serie no reconocida: %r" % raw)
    return serie, warn


def serie_dir(serie):
    return cache_root() / serie


def source_info(serie):
    p = serie_dir(serie) / "SOURCE.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def addons_paths(serie):
    """Directorios donde buscar modulos, en orden de prioridad."""
    root = serie_dir(serie)
    info = source_info(serie)
    if info and info.get("addons_paths"):
        return [pathlib.Path(p) for p in info["addons_paths"] if pathlib.Path(p).is_dir()]
    out = []
    for rel in ("odoo/addons", "addons"):
        d = root / rel
        if d.is_dir():
            out.append(d)
    return out


def _download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        cmd = ["curl", "-fL", "--no-progress-meter", "--retry", "3", "--retry-delay", "2",
               "-C", "-", "-o", str(dest), url]
        print("  $ %s" % " ".join(cmd), file=sys.stderr)
        res = subprocess.run(cmd)
        if res.returncode != 0:
            raise RuntimeError("curl fallo con codigo %s para %s" % (res.returncode, url))
        return
    import urllib.request
    print("  descargando %s" % url, file=sys.stderr)
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _sha256(path, limit_mb=None):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_ensure(a):
    serie, warn = normalize_serie(a.serie)
    target = serie_dir(serie)
    if target.is_dir() and (target / "SOURCE.json").exists() and not a.force:
        info = source_info(serie)
        info["cached"] = True
        info["warning"] = warn
        return _out(info)

    if target.exists() and a.force:
        shutil.rmtree(target)

    urls = [NIGHTLY.format(serie=serie)]
    if a.github:
        urls.insert(0, GITHUB_FALLBACK.format(serie=serie))
    else:
        urls.append(GITHUB_FALLBACK.format(serie=serie))

    zip_path = cache_root() / "downloads" / ("odoo_%s.zip" % serie)
    used = None
    errors = []
    for url in urls:
        try:
            print("Descargando fuente de Odoo %s ..." % serie, file=sys.stderr)
            _download(url, zip_path)
            used = url
            break
        except Exception as exc:  # noqa: BLE001
            errors.append("%s -> %s" % (url, exc))
            if zip_path.exists():
                zip_path.unlink()
    if not used:
        raise SystemExit("No se pudo descargar la fuente de %s:\n  %s"
                         % (serie, "\n  ".join(errors)))

    print("Descomprimiendo (%.0f MB) ..." % (zip_path.stat().st_size / 1e6), file=sys.stderr)
    staging = cache_root() / (".staging-%s" % serie)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(staging)

    children = [p for p in staging.iterdir() if p.is_dir()]
    root = children[0] if len(children) == 1 else staging
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root), str(target))
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    paths = []
    for rel in ("odoo/addons", "addons"):
        d = target / rel
        if d.is_dir():
            paths.append(str(d))
    info = {
        "serie": serie,
        "root": str(target),
        "addons_paths": paths,
        "modules": sum(len([p for p in pathlib.Path(d).iterdir()
                            if (p / "__manifest__.py").exists()]) for d in paths),
        "url": used,
        "sha256": _sha256(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "edition": "community",
        "note": "Nightly Community. Los modulos Enterprise no se publican.",
    }
    (target / "SOURCE.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    if not a.keep_zip:
        zip_path.unlink(missing_ok=True)
    info["cached"] = False
    info["warning"] = warn
    _out(info)


def cmd_path(a):
    serie, warn = normalize_serie(a.serie)
    info = source_info(serie)
    if not info:
        raise SystemExit("La serie %s no esta cacheada. Ejecuta: "
                         "python3 odoo_source.py ensure %s" % (serie, serie))
    info["addons_paths"] = [str(p) for p in addons_paths(serie)]
    info["warning"] = warn
    _out(info)


def cmd_list(a):
    root = cache_root()
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "SOURCE.json").exists():
                out.append(json.loads((d / "SOURCE.json").read_text(encoding="utf-8")))
    _out({"cache": str(root), "series": out})


def _rg(pattern, paths, extra=None, limit=80):
    if not paths:
        raise SystemExit("No hay fuente cacheada para esa serie.")
    if shutil.which("rg"):
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never",
               "--max-count", "5", "-e", pattern]
    else:
        cmd = ["grep", "-rn", "-E", pattern]
    cmd += (extra or [])
    cmd += [str(p) for p in paths]
    res = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l for l in res.stdout.splitlines() if l.strip()]
    return lines[:limit], len(lines)


def cmd_find_model(a):
    serie, _ = normalize_serie(a.serie)
    paths = addons_paths(serie)
    model = a.model
    esc = re.escape(model)
    defs, _n = _rg(r"_name\s*=\s*[\"']%s[\"']" % esc, paths, ["-g", "*.py"])
    inherits, _n2 = _rg(r"_inherit\s*=\s*[\"']%s[\"']|_inherit\s*=\s*\[[^\]]*[\"']%s[\"']"
                        % (esc, esc), paths, ["-g", "*.py"])
    _out({
        "serie": serie,
        "model": model,
        "definition": defs,
        "extensions": inherits,
        "hint": "La definicion marca el modulo que crea el modelo; las extensiones, "
                "que modulos le anaden campos o cambian su comportamiento.",
    })


def cmd_grep(a):
    serie, _ = normalize_serie(a.serie)
    paths = addons_paths(serie)
    if a.modules:
        base = paths
        paths = []
        for mod in a.modules.split(","):
            for b in base:
                d = b / mod.strip()
                if d.is_dir():
                    paths.append(d)
        if not paths:
            raise SystemExit("Ningun modulo encontrado entre: %s" % a.modules)
    extra = []
    if a.glob:
        extra += ["-g", a.glob]
    lines, total = _rg(a.pattern, paths, extra, limit=a.limit)
    _out({"serie": serie, "pattern": a.pattern, "matches": lines,
          "shown": len(lines), "total": total})


def cmd_module(a):
    serie, _ = normalize_serie(a.serie)
    for base in addons_paths(serie):
        d = base / a.module
        manifest = d / "__manifest__.py"
        if manifest.exists():
            try:
                data = ast.literal_eval(manifest.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                data = {"_error": "manifiesto no evaluable como literal"}
            files = sorted(
                str(p.relative_to(d)) for p in d.rglob("*")
                if p.is_file() and p.suffix in (".py", ".xml", ".csv")
                and "/static/" not in str(p))
            return _out({
                "serie": serie, "module": a.module, "path": str(d),
                "depends": data.get("depends"), "summary": data.get("summary"),
                "category": data.get("category"), "version": data.get("version"),
                "data_files": data.get("data"),
                "files": files[:400], "file_count": len(files),
            })
    raise SystemExit("El modulo %r no esta en la fuente de %s (puede ser Enterprise, "
                     "OCA o a medida: revisalo con odoo_probe.py modules)."
                     % (a.module, serie))


def _out(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("ensure", help="descarga y descomprime la serie si falta")
    c.add_argument("serie")
    c.add_argument("--force", action="store_true", help="vuelve a descargar aunque este")
    c.add_argument("--keep-zip", action="store_true")
    c.add_argument("--github", action="store_true", help="probar antes el zip de GitHub")
    c.set_defaults(func=cmd_ensure)

    c = sub.add_parser("path"); c.add_argument("serie"); c.set_defaults(func=cmd_path)
    c = sub.add_parser("list"); c.set_defaults(func=cmd_list)

    c = sub.add_parser("find-model", help="donde se define y donde se extiende un modelo")
    c.add_argument("model"); c.add_argument("--serie", required=True)
    c.set_defaults(func=cmd_find_model)

    c = sub.add_parser("grep", help="busca en la fuente de una serie")
    c.add_argument("pattern"); c.add_argument("--serie", required=True)
    c.add_argument("--modules", help="lista separada por comas: mrp,stock")
    c.add_argument("--glob", help="filtro de fichero, p.ej. '*.py'")
    c.add_argument("--limit", type=int, default=80)
    c.set_defaults(func=cmd_grep)

    c = sub.add_parser("module", help="manifiesto y ficheros de un modulo")
    c.add_argument("module"); c.add_argument("--serie", required=True)
    c.set_defaults(func=cmd_module)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
