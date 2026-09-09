"""Register and verify an Odoo instance (read-only).

Everything is driven by flags: there is no interactive assistant, because the
place this runs from (Claude Code's `!` prefix, a hook, a script) has no real
terminal. Claude asks the person for the data and calls this.

The short path, one command:

    printf '%s' 'la-clave' | python3 odoo_connect.py setup \
        --url erp.cliente.com --db produccion --user consultor

    -> discovers protocol, port, version and edition, saves the instance,
       stores the password with mode 600, verifies the access and downloads
       the source of the detected series.

The password comes in through STDIN (or ODOO_PASSWORD), never through argv,
where `ps` and the shell history would pick it up.

The long path, step by step, when something needs to be done by hand:

  1) probe --url erp.cliente.com   -> version, edition and, when the server allows
                                      it, the list of databases. No credentials.
  2) save --instance cliente ...   -> writes instances/cliente/instance.json.
  3) set-password --instance cliente (password through STDIN).
  4) verify --instance cliente     -> authenticates and stores series and edition.
"""
import argparse
import contextlib
import datetime
import io
import re
import json
import os
import pathlib
import stat
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from odoo_ro import OdooRO, instance_dir, list_instances, project_root  # noqa: E402
import odoo_source  # noqa: E402

INSTANCES_GITIGNORE = """# Nunca versionar credenciales de instancias de cliente.
.env
*/.env
**/.env
"""


def _out(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def cmd_probe(a):
    """Server version and available databases. Needs no credentials.

    With --url the protocol and the port are guessed and tried in order; with
    --host they are taken as given.
    """
    if not a.url and not a.host:
        raise SystemExit("Indica --url erp.cliente.com (o --host con --protocol y --port).")
    if a.url:
        info = discover(a.url, timeout=a.timeout)
        if not info["ok"]:
            _out(info)
            raise SystemExit(1)
        return _out(info)
    odoo = OdooRO(host=a.host, user="", password="", port=a.port,
                  protocol=a.protocol, timeout=a.timeout)
    version = odoo.version()
    dbs = odoo.list_databases()
    _out({
        "url": odoo.url,
        "host": odoo.host,
        "port": odoo.port,
        "protocol": odoo.protocol,
        "server_version": version.get("server_version"),
        "serie": odoo.server_serie(),
        "edition": "enterprise" if odoo.is_enterprise() else "community",
        "databases": dbs,
        "databases_listing": "disponible" if dbs is not None else
                             "deshabilitada en el servidor (list_db=False): hay que saber el nombre",
    })


def cmd_save(a):
    d = instance_dir(a.instance, a.project)
    d.mkdir(parents=True, exist_ok=True)
    gitignore = d.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(INSTANCES_GITIGNORE, encoding="utf-8")
    conf_path = d / "instance.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
    conf.update({
        "slug": a.instance,
        "host": a.host or conf.get("host"),
        "port": a.port or conf.get("port"),
        "protocol": a.protocol or conf.get("protocol") or "http",
        "db": a.db or conf.get("db"),
        "user": a.user or conf.get("user"),
        "timeout": a.timeout,
        "read_only": True,
        "created_at": conf.get("created_at") or _now(),
        "updated_at": _now(),
    })
    if a.label:
        conf["label"] = a.label
    missing = [k for k in ("host", "db", "user") if not conf.get(k)]
    conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "processes").mkdir(exist_ok=True)
    _out({
        "written": str(conf_path),
        "instance": conf,
        "missing": missing,
        "next": "Falta guardar la contrasena: printf '%%s' 'la-clave' | "
                "python3 odoo_connect.py set-password --instance %s" % a.instance,
    })


def cmd_set_password(a):
    """Read the password from STDIN. Never from argv: it would leak into ps and
    into the shell history.
    """
    d = instance_dir(a.instance, a.project)
    if not (d / "instance.json").exists():
        raise SystemExit("No existe instances/%s. Ejecuta antes 'save'." % a.instance)
    password = "" if sys.stdin.isatty() else sys.stdin.read().rstrip("\r\n")
    password = password or os.environ.get("ODOO_PASSWORD") or ""
    if not password:
        raise SystemExit(
            "No llego ninguna contrasena. Pasala por STDIN, nunca por argv:\n"
            "  printf '%%s' 'la-clave' | python3 %s set-password --instance %s"
            % (__file__, a.instance))
    env_path = d / ".env"
    env_path.write_text("PASSWORD=%s\n" % password, encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    _out({"written": str(env_path), "mode": "600", "length": len(password)})


def cmd_verify(a):
    odoo = OdooRO.from_instance(a.instance, a.project, connect=True)
    summary = odoo.summary()
    d = instance_dir(a.instance, a.project)
    conf_path = d / "instance.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    conf.update({
        "serie": summary["serie"],
        "edition": summary["edition"],
        "server_version": summary["server_version"],
        "uid": summary["uid"],
        "verified_at": _now(),
        "updated_at": _now(),
    })
    conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False), encoding="utf-8")
    user = odoo.search_read("res.users", [("id", "=", odoo.uid)],
                            ["name", "login", "share", "company_id"], limit=1)
    summary["odoo_user"] = user[0] if user else None
    summary["source_hint"] = (
        "Descarga la fuente con: python3 odoo_source.py ensure %s" % summary["serie"])
    if summary["edition"] == "enterprise":
        summary["enterprise_note"] = (
            "La instancia es Enterprise. El nightly publico solo trae Community: "
            "los modulos enterprise se documentan desde los metadatos de la "
            "instancia, no desde el codigo fuente.")
    _out(summary)


def cmd_list(a):
    root = project_root(a.project)
    out = []
    for slug in list_instances(a.project):
        conf = json.loads((instance_dir(slug, a.project) / "instance.json")
                          .read_text(encoding="utf-8"))
        conf.pop("password", None)
        conf["has_password"] = (instance_dir(slug, a.project) / ".env").exists() \
            or bool(os.environ.get("ODOO_PASSWORD"))
        procs = instance_dir(slug, a.project) / "processes"
        conf["processes"] = sorted(p.name for p in procs.iterdir() if p.is_dir()) \
            if procs.is_dir() else []
        out.append(conf)
    _out({"project": str(root), "instances": out})



# --- Deteccion de la direccion del servidor ----------------------------------
def url_candidates(raw):
    """Turn whatever the user typed into an ordered list of (protocol, host, port).

    Accepts 'erp.acme.com', 'https://erp.acme.com', '1.2.3.4:8069', 'http://x/web'.
    When the scheme or the port are missing we do not ask: we return the plausible
    combinations so the caller can try them until one answers.
    """
    raw = (raw or "").strip()
    protocol = ""
    if "://" in raw:
        protocol, _, raw = raw.partition("://")
        protocol = protocol.lower().strip()
    raw = raw.strip("/").split("/")[0]
    host, _, port = raw.partition(":")
    host, port = host.strip().lower(), port.strip()
    if not host:
        raise SystemExit("No entiendo la direccion %r. Ejemplo: erp.cliente.com" % raw)
    if protocol not in ("", "http", "https"):
        raise SystemExit("Protocolo no soportado: %r (solo http o https)." % protocol)
    if protocol and port:
        return [(protocol, host, port)]
    if protocol:
        first = "443" if protocol == "https" else "80"
        return [(protocol, host, first), (protocol, host, "8069")]
    if port:
        return [("https" if port == "443" else "http", host, port)]
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
        # Una IP suelta casi siempre es un Odoo sin proxy delante.
        return [("http", host, "8069"), ("https", host, "443"), ("http", host, "80")]
    return [("https", host, "443"), ("http", host, "8069"), ("http", host, "80")]


def discover(raw_url, timeout=20):
    """Probe every candidate for `raw_url` and describe the first one that answers.

    Needs no credentials: it only calls /xmlrpc/2/common.version() and, when the
    server allows it, db.list().
    """
    tried = []
    candidates = url_candidates(raw_url)
    # Con varios candidatos no se puede esperar el timeout completo en cada uno:
    # un puerto cerrado se cuelga hasta agotarlo.
    per_try = timeout if len(candidates) == 1 else min(timeout, 12)
    for protocol, host, port in candidates:
        odoo = OdooRO(host=host, user="", password="", port=port,
                      protocol=protocol, timeout=per_try)
        try:
            version = odoo.version()
        except Exception as exc:  # noqa: BLE001
            tried.append({"url": odoo.url, "error": str(exc)[:200]})
            continue
        dbs = odoo.list_databases()
        return {
            "ok": True,
            "url": odoo.url,
            "host": host,
            "port": port,
            "protocol": protocol,
            "server_version": version.get("server_version"),
            "serie": odoo.server_serie(),
            "edition": "enterprise" if odoo.is_enterprise() else "community",
            "databases": dbs,
            "databases_listing": "disponible" if dbs is not None else
                                 "deshabilitada en el servidor (list_db=False): "
                                 "hay que saber el nombre exacto",
            "tried": tried,
        }
    return {
        "ok": False,
        "tried": tried,
        "error": "Ninguna direccion respondio. Revisa el dominio y el puerto, y si "
                 "hace falta VPN para llegar al servidor.",
    }


def _slugify(text, fallback="odoo"):
    return re.sub(r"[^a-z0-9-]+", "-", str(text).lower()).strip("-")[:24] or fallback


# --- Alta completa ------------------------------------------------------------
def _read_password():
    """STDIN when it is piped, ODOO_PASSWORD otherwise. Never argv."""
    password = "" if sys.stdin.isatty() else sys.stdin.read().rstrip("\r\n")
    return password or os.environ.get("ODOO_PASSWORD") or ""


def cmd_setup(a):
    """Register an instance end to end: address, database, user, password, source.

    There are no questions here on purpose: whoever calls this (Claude, a script)
    already has the answers, and the `!` prefix of Claude Code gives no terminal to
    ask from. What can be discovered is discovered -- protocol, port, version,
    edition and, when the server publishes them, the databases -- and what cannot
    is required as a flag.
    """
    steps = []

    def say(msg=""):
        if not a.json:
            print(msg)

    say("\n  Alta de una instancia Odoo (solo lectura)")
    say("  " + "-" * 44)
    say("  Nada de lo que hagamos aqui modifica la instancia.\n")

    say("  Buscando el servidor en %s ..." % a.url)
    info = discover(a.url, timeout=a.timeout)
    if not info["ok"]:
        detail = "\n".join("    %s -> %s" % (t["url"], t["error"]) for t in info["tried"])
        raise SystemExit("\n  %s\n%s" % (info["error"], detail))
    steps.append({"paso": "servidor", "url": info["url"],
                  "server_version": info["server_version"], "edition": info["edition"]})
    say("  Encontrado en %s: Odoo %s (%s)\n"
        % (info["url"], info["server_version"], info["edition"]))

    dbs = info["databases"]
    db = a.db
    if not db:
        if dbs and len(dbs) == 1:
            db = dbs[0]
            say("  El servidor solo publica una base: %s\n" % db)
        elif dbs:
            raise SystemExit(
                "Falta --db. Pregunta cual de estas quiere consultar: %s" % ", ".join(dbs))
        else:
            raise SystemExit(
                "Falta --db. El servidor no publica la lista de bases (list_db=False): "
                "hay que preguntarle el nombre exacto a la persona.")
    elif dbs and db not in dbs:
        say("  Aviso: %r no esta entre las bases que publica el servidor (%s)."
            % (db, ", ".join(dbs)))

    user = a.user

    password = _read_password()
    if not password:
        raise SystemExit(
            "Falta la contrasena. Pasala por STDIN, nunca por argv:\n"
            "  printf '%%s' 'la-clave' | python3 %s setup --url %s --db %s --user %s"
            % (__file__, a.url, db, user))

    slug = a.instance or _slugify(info["host"])
    label = a.label or info["host"]

    class _Args:
        pass
    args = _Args()
    args.project = a.project
    args.instance = slug
    args.host = info["host"]
    args.port = info["port"]
    args.protocol = info["protocol"]
    args.db = db
    args.user = user
    args.label = label
    args.timeout = max(a.timeout, 60)
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_save(args)

    d = instance_dir(slug, a.project)
    env_path = d / ".env"
    env_path.write_text("PASSWORD=%s\n" % password, encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    steps.append({"paso": "guardado", "instancia": slug,
                  "config": str(d / "instance.json"), "password": str(env_path)})

    say("  Verificando el acceso...")
    try:
        odoo = OdooRO.from_instance(slug, a.project, connect=True)
    except SystemExit as exc:
        raise SystemExit(
            "\n  Los datos se guardaron en %s, pero el acceso fallo:\n  %s\n\n"
            "  Corrige lo que falle y repite: se sobrescribe sin problema." % (d, exc))
    summary = odoo.summary()
    conf_path = d / "instance.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    conf.update({"serie": summary["serie"], "edition": summary["edition"],
                 "server_version": summary["server_version"], "uid": summary["uid"],
                 "verified_at": _now(), "updated_at": _now()})
    conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False), encoding="utf-8")
    steps.append({"paso": "verificado", "uid": summary["uid"], "serie": summary["serie"],
                  "edition": summary["edition"]})
    say("  Acceso correcto como uid %s.\n" % summary["uid"])

    serie = summary["serie"]
    base_serie = odoo_source.normalize_serie(serie)[0]
    if odoo_source.source_info(base_serie):
        say("  El codigo fuente de Odoo %s ya estaba descargado." % base_serie)
        steps.append({"paso": "fuente", "estado": "ya-estaba", "serie": base_serie})
    elif a.no_source:
        say("  Falta el codigo fuente de Odoo %s: sin el no se puede explicar como"
            % base_serie)
        say("  funcionan los procesos. Descargalo con: odoo_source.py ensure %s"
            % base_serie)
        steps.append({"paso": "fuente", "estado": "omitida", "serie": base_serie})
    else:
        say("  Descargando el codigo fuente de Odoo %s (~370 MB, solo la primera"
            % base_serie)
        say("  vez para esta version)...")
        args2 = _Args()
        args2.serie = serie
        args2.force = args2.keep_zip = args2.github = False
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                odoo_source.cmd_ensure(args2)
            say("  Fuente lista.")
            steps.append({"paso": "fuente", "estado": "descargada", "serie": base_serie})
        except SystemExit as exc:
            say("  No se pudo descargar la fuente: %s" % exc)
            steps.append({"paso": "fuente", "estado": "error", "detalle": str(exc)})

    if summary["edition"] == "enterprise":
        say("\n  Aviso: la instancia es Enterprise y el nightly publico solo trae")
        say("  Community. Los modulos enterprise se documentan desde la instancia.")

    if a.json:
        _out({"ok": True, "instancia": slug, "resumen": summary, "db": db,
              "directorio": str(d), "pasos": steps})
        return

    print("\n  " + "-" * 44)
    print("  Listo. Instancia '%s' dada de alta." % slug)
    print("  Odoo %s %s, base '%s', usuario '%s'."
          % (summary["serie"], summary["edition"], db, user))
    print("  La contrasena quedo en %s, solo legible por ti (permisos 600)." % env_path)
    print("  Es un fichero de credenciales: no compartas la carpeta instances/, no la")
    print("  subas a git (ya esta ignorada) y no pegues su contenido en ningun sitio.")
    print()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="raiz del proyecto (por defecto, el cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("probe", help="version y bases del servidor, sin credenciales")
    c.add_argument("--url", help="dominio, ip o url completa; adivina protocolo y puerto")
    c.add_argument("--host", help="alternativa a --url, con --protocol y --port explicitos")
    c.add_argument("--port")
    c.add_argument("--protocol", default="http", choices=["http", "https"])
    c.add_argument("--timeout", type=int, default=30)
    c.set_defaults(func=cmd_probe)

    c = sub.add_parser("setup", help="alta completa en un comando: sondeo, guardado, verificacion y fuente")
    c.add_argument("--url", required=True, help="dominio, ip o url completa de la instancia")
    c.add_argument("--db", help="base de datos; solo se puede omitir si el servidor "
                                "publica una unica base")
    c.add_argument("--user", required=True, help="login del usuario de Odoo")
    c.add_argument("--instance", help="nombre corto de la carpeta; por defecto, el dominio")
    c.add_argument("--label", help="nombre legible del cliente o entorno")
    c.add_argument("--no-source", action="store_true",
                   help="no descargar el codigo fuente de la serie detectada")
    c.add_argument("--json", action="store_true", help="salida JSON en vez de texto")
    c.add_argument("--timeout", type=int, default=30)
    c.set_defaults(func=cmd_setup)

    c = sub.add_parser("save", help="crea o actualiza instances/<slug>/instance.json")
    c.add_argument("--instance", required=True)
    c.add_argument("--host")
    c.add_argument("--port")
    c.add_argument("--protocol", choices=["http", "https"])
    c.add_argument("--db")
    c.add_argument("--user")
    c.add_argument("--label", help="nombre legible del cliente o entorno")
    c.add_argument("--timeout", type=int, default=60)
    c.set_defaults(func=cmd_save)

    c = sub.add_parser("set-password", help="guarda la contrasena leyendola de STDIN")
    c.add_argument("--instance", required=True)
    c.set_defaults(func=cmd_set_password)

    c = sub.add_parser("verify", help="autentica y detecta serie y edicion")
    c.add_argument("--instance", required=True)
    c.set_defaults(func=cmd_verify)

    c = sub.add_parser("list", help="instancias dadas de alta en este proyecto")
    c.set_defaults(func=cmd_list)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
