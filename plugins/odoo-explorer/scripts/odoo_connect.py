"""Alta y verificacion de una instancia Odoo (solo lectura).

Flujo pensado para que la contrasena NUNCA pase por el chat:

  1) python3 odoo_connect.py probe --host erp.cliente.com --protocol https
     -> version del servidor y, si el servidor lo permite, lista de bases.

  2) python3 odoo_connect.py save --instance cliente --host erp.cliente.com \
         --protocol https --db produccion --user consultor
     -> escribe instances/cliente/instance.json (sin contrasena).

  3) El USUARIO ejecuta, en su terminal:
     read -rsp 'Password Odoo: ' P && printf '%s' "$P" | \
         python3 odoo_connect.py set-password --instance cliente; unset P
     -> escribe instances/cliente/.env con chmod 600.

  4) python3 odoo_connect.py verify --instance cliente
     -> autentica, detecta serie (18.0) y edicion (community/enterprise),
        y actualiza instance.json.
"""
import argparse
import contextlib
import datetime
import getpass
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
    """Version del servidor y bases disponibles. No requiere credenciales."""
    odoo = OdooRO(host=a.host, user="", password="", port=a.port,
                  protocol=a.protocol, timeout=a.timeout)
    version = odoo.version()
    dbs = odoo.list_databases()
    _out({
        "url": odoo.url,
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
        "next": "El usuario debe guardar la contrasena: read -rsp 'Password: ' P && "
                "printf '%%s' \"$P\" | python3 odoo_connect.py set-password --instance %s; unset P"
                % a.instance,
    })


def cmd_set_password(a):
    """Lee la contrasena de STDIN. Nunca por argv (quedaria en ps y en el historial)."""
    d = instance_dir(a.instance, a.project)
    if not (d / "instance.json").exists():
        raise SystemExit("No existe instances/%s. Ejecuta antes 'save'." % a.instance)
    if sys.stdin.isatty():
        raise SystemExit(
            "La contrasena se pasa por STDIN, no de forma interactiva. Ejecuta:\n"
            "  read -rsp 'Password Odoo: ' P && printf '%%s' \"$P\" | "
            "python3 %s set-password --instance %s; unset P" % (__file__, a.instance))
    password = sys.stdin.read().rstrip("\r\n")
    if not password:
        raise SystemExit("No llego ninguna contrasena por STDIN.")
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



# --- Asistente interactivo (lo ejecuta el usuario, no Claude) ----------------
def _ask(prompt, default=None, required=True):
    suffix = " [%s]" % default if default else ""
    while True:
        val = input("%s%s: " % (prompt, suffix)).strip()
        if not val and default is not None:
            return default
        if val or not required:
            return val
        print("  Hace falta un valor.")


def _ask_choice(prompt, options, default=None):
    for i, opt in enumerate(options, 1):
        print("   %d) %s" % (i, opt))
    while True:
        raw = _ask(prompt, default=default)
        if raw in options:
            return raw
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Elige un numero de la lista, o escribe el nombre.")


def cmd_wizard(a):
    """Alta guiada de una instancia. Requiere terminal interactiva."""
    if not sys.stdin.isatty():
        raise SystemExit(
            "El asistente necesita una terminal. Ejecutalo tu mismo escribiendo\n"
            "  ! python3 %s wizard\n"
            "en el prompt de Claude Code, o directamente en tu terminal." % __file__)

    print("\n  Alta de una instancia Odoo (solo lectura)")
    print("  " + "-" * 44)
    print("  Nada de lo que hagamos aqui modifica la instancia.\n")

    host = _ask("  Dominio o IP del servidor (sin http://)")
    host = host.replace("https://", "").replace("http://", "").strip("/")
    if ":" in host:
        host, _, guess_port = host.partition(":")
    else:
        guess_port = ""
    protocol = _ask("  Protocolo (http/https)",
                    default="https" if not guess_port else "http")
    port = _ask("  Puerto", default=guess_port or ("443" if protocol == "https" else "8069"))

    print("\n  Probando la conexion con el servidor...")
    probe = OdooRO(host=host, user="", password="", port=port,
                   protocol=protocol, timeout=30)
    try:
        version = probe.version()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "\n  No se pudo hablar con %s.\n  Detalle: %s\n\n"
            "  Revisa el dominio, el puerto y si hace falta VPN." % (probe.url, exc))
    serie = probe.server_serie()
    edition = "Enterprise" if probe.is_enterprise() else "Community"
    print("  Conectado. Odoo %s (%s)\n" % (version.get("server_version"), edition))

    dbs = probe.list_databases()
    if dbs:
        print("  Bases de datos que expone el servidor:")
        db = _ask_choice("  Cual quieres consultar", dbs, default="1")
    else:
        print("  El servidor no publica la lista de bases (es lo normal en produccion).")
        db = _ask("  Nombre exacto de la base de datos")

    user = _ask("\n  Usuario de Odoo con el que conectarte")
    password = getpass.getpass("  Contrasena (no se muestra al teclear): ")
    if not password:
        raise SystemExit("  Sin contrasena no se puede continuar.")

    default_slug = re.sub(r"[^a-z0-9-]+", "-", host.lower()).strip("-")[:24]
    slug = _ask("\n  Nombre corto para esta instancia", default=default_slug)
    label = _ask("  Nombre legible (para los informes)", default=host, required=False)

    class _Args:
        pass
    args = _Args()
    args.project = a.project
    args.instance = slug
    args.host = host
    args.port = port
    args.protocol = protocol
    args.db = db
    args.user = user
    args.label = label
    args.timeout = 60
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_save(args)

    d = instance_dir(slug, a.project)
    env_path = d / ".env"
    env_path.write_text("PASSWORD=%s\n" % password, encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    print("\n  Verificando el acceso...")
    try:
        odoo = OdooRO.from_instance(slug, a.project, connect=True)
    except SystemExit as exc:
        raise SystemExit(
            "\n  Los datos se guardaron, pero el acceso fallo:\n  %s\n\n"
            "  Corrige y repite el asistente: se sobrescribe sin problema." % exc)
    summary = odoo.summary()
    conf_path = d / "instance.json"
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    conf.update({"serie": summary["serie"], "edition": summary["edition"],
                 "server_version": summary["server_version"], "uid": summary["uid"],
                 "verified_at": _now(), "updated_at": _now()})
    conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  Acceso correcto como uid %s.\n" % summary["uid"])

    serie = summary["serie"]
    cached = odoo_source.source_info(odoo_source.normalize_serie(serie)[0])
    if cached:
        print("  El codigo fuente de Odoo %s ya esta descargado." % serie)
    else:
        print("  Falta el codigo fuente de Odoo %s. Son unos 370 MB y se descarga" % serie)
        print("  una sola vez: sin el, no se puede explicar como funcionan los procesos.")
        if _ask("  Descargar ahora (si/no)", default="si").lower().startswith("s"):
            print()
            args2 = _Args()
            args2.serie = serie
            args2.force = False
            args2.keep_zip = False
            args2.github = False
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                odoo_source.cmd_ensure(args2)
            print("\n  Fuente lista.")
        else:
            print("  Puedes descargarla despues pidiendoselo a Claude.")

    print("\n  " + "-" * 44)
    print("  Listo. Instancia '%s' dada de alta." % slug)
    print("  Odoo %s %s, base '%s'." % (summary["serie"], summary["edition"], db))
    print("  La contrasena quedo en %s, solo legible por ti." % env_path)
    print("\n  Ahora, en Claude Code, ya puedes pedir cosas como:")
    print("    /odoo-process manufactura")
    print("    /odoo-report ventas por cliente este ano")
    print()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="raiz del proyecto (por defecto, el cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("probe", help="version y bases del servidor, sin credenciales")
    c.add_argument("--host", required=True)
    c.add_argument("--port")
    c.add_argument("--protocol", default="http", choices=["http", "https"])
    c.add_argument("--timeout", type=int, default=30)
    c.set_defaults(func=cmd_probe)

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

    c = sub.add_parser("wizard", help="alta guiada paso a paso (la ejecuta el usuario)")
    c.set_defaults(func=cmd_wizard)

    c = sub.add_parser("list", help="instancias dadas de alta en este proyecto")
    c.set_defaults(func=cmd_list)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
