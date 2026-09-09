"""Register and verify an Odoo instance (read-only).

The short path (one command, everything else is discovered or asked):

    python3 odoo_connect.py setup --url https://erp.cliente.com
    -> asks database, user and password (hidden), verifies the access, detects
       the series and the edition, and downloads the source of that series.

Claude can drive the same command without a terminal, piping the password so it
never reaches argv (where ps and the shell history would pick it up):

    printf '%s' 'la-clave' | python3 odoo_connect.py setup \
        --url https://erp.cliente.com --db produccion --user consultor

Or, when the person prefers to type it hidden instead of dictating it:

    read -rsp 'Password Odoo: ' P && printf '%s' "$P" | \
        python3 odoo_connect.py setup --url https://erp.cliente.com \
            --db produccion --user consultor; unset P

The long path, step by step, when something needs to be done by hand:

  1) probe --url erp.cliente.com   -> version, edition and, when the server allows
                                      it, the list of databases. No credentials.
  2) save --instance cliente ...   -> writes instances/cliente/instance.json.
  3) set-password --instance cliente (password through STDIN, never argv).
  4) verify --instance cliente     -> authenticates and stores series and edition.
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
        "next": "El usuario debe guardar la contrasena: read -rsp 'Password: ' P && "
                "printf '%%s' \"$P\" | python3 odoo_connect.py set-password --instance %s; unset P"
                % a.instance,
    })


def cmd_set_password(a):
    """Read the password from STDIN. Never from argv: it would leak into ps and
    into the shell history.
    """
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


# --- Preguntas sencillas (solo cuando hay terminal) --------------------------
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


def _ask_yes(prompt, default="si"):
    return _ask(prompt, default=default).strip().lower().startswith(("s", "y"))


def _read_password(tty, prompt="  Contrasena (no se muestra al teclear): "):
    """STDIN when it is piped, ODOO_PASSWORD otherwise, and only then the prompt."""
    if not tty:
        password = sys.stdin.read().rstrip("\r\n")
        if password:
            return password
    env = os.environ.get("ODOO_PASSWORD")
    if env:
        return env
    if tty:
        return getpass.getpass(prompt)
    return ""


def cmd_setup(a):
    """Register an instance end to end: address, database, user, password, source.

    Whatever can be discovered is discovered (protocol, port, version, edition and,
    when the server publishes them, the databases). Whatever cannot is asked with a
    plain prompt. Claude can also drive it without a terminal by passing --url,
    --db and --user and piping the password through STDIN.
    """
    tty = sys.stdin.isatty()
    steps = []

    def say(msg=""):
        if not a.json:
            print(msg)

    say("\n  Alta de una instancia Odoo (solo lectura)")
    say("  " + "-" * 44)
    say("  Nada de lo que hagamos aqui modifica la instancia.\n")

    raw_url = a.url
    if not raw_url:
        if not tty:
            raise SystemExit("Falta --url (por ejemplo: --url https://erp.cliente.com).")
        raw_url = _ask("  Direccion del servidor (dominio, ip o url completa)")

    say("  Buscando el servidor en %s ..." % raw_url)
    info = discover(raw_url, timeout=a.timeout)
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
            if not tty:
                raise SystemExit(
                    "Falta --db. El servidor publica estas bases: %s" % ", ".join(dbs))
            say("  Bases de datos que publica el servidor:")
            db = _ask_choice("  Cual quieres consultar", dbs, default="1")
        else:
            if not tty:
                raise SystemExit(
                    "Falta --db. El servidor no publica la lista de bases "
                    "(list_db=False): hay que saber el nombre exacto.")
            say("  El servidor no publica la lista de bases (normal en produccion).")
            db = _ask("  Nombre exacto de la base de datos")
    elif dbs and db not in dbs:
        say("  Aviso: %r no esta entre las bases que publica el servidor (%s)."
            % (db, ", ".join(dbs)))

    user = a.user or (_ask("\n  Usuario de Odoo con el que conectarte") if tty else "")
    if not user:
        raise SystemExit("Falta --user (el login del usuario de Odoo).")

    password = _read_password(tty)
    if not password:
        raise SystemExit(
            "Falta la contrasena. Pasala por STDIN (nunca por argv):\n"
            "  printf '%%s' 'la-clave' | python3 %s setup --url %s --db %s --user %s\n"
            "O que la teclee la persona, oculta:\n"
            "  read -rsp 'Password Odoo: ' P && printf '%%s' \"$P\" | "
            "python3 %s setup --url %s --db %s --user %s; unset P"
            % (__file__, raw_url, db, user, __file__, raw_url, db, user))

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

    say("\n  Verificando el acceso...")
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
    cached = odoo_source.source_info(base_serie)
    if cached:
        say("  El codigo fuente de Odoo %s ya estaba descargado." % base_serie)
        steps.append({"paso": "fuente", "estado": "ya-estaba", "serie": base_serie})
    elif a.no_source:
        steps.append({"paso": "fuente", "estado": "omitida", "serie": base_serie})
    else:
        say("  Falta el codigo fuente de Odoo %s. Son unos 370 MB y se descarga"
            % base_serie)
        say("  una sola vez: sin el no se puede explicar como funcionan los procesos.")
        if tty and not _ask_yes("  Descargar ahora (si/no)"):
            say("  Puedes descargarla despues pidiendoselo a Claude.")
            steps.append({"paso": "fuente", "estado": "rechazada", "serie": base_serie})
        else:
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
    print("\n  Vuelve a Claude Code y pide lo que necesites, por ejemplo:")
    print("    /odoo-process compras")
    print("    /odoo-report facturas sin pagar")
    print()


def cmd_wizard(a):
    """Same as `setup`, asking everything from scratch. Needs a terminal."""
    if not sys.stdin.isatty():
        raise SystemExit(
            "El asistente necesita una terminal. Escribe tu mismo, en el prompt de "
            "Claude Code,\n  ! python3 %s setup\ny contesta las preguntas." % __file__)
    a.url = getattr(a, "url", None)
    a.db = getattr(a, "db", None)
    a.user = getattr(a, "user", None)
    a.instance = getattr(a, "instance", None)
    a.label = getattr(a, "label", None)
    return cmd_setup(a)


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

    c = sub.add_parser("setup", help="alta completa: descubre lo que puede y pregunta el resto")
    c.add_argument("--url", help="dominio, ip o url completa de la instancia")
    c.add_argument("--db", help="base de datos; se pregunta o se deduce si falta")
    c.add_argument("--user", help="login del usuario de Odoo")
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

    c = sub.add_parser("wizard", help="alias de setup sin datos previos (lo ejecuta el usuario)")
    c.add_argument("--no-source", action="store_true")
    c.add_argument("--json", action="store_true")
    c.add_argument("--timeout", type=int, default=30)
    c.set_defaults(func=cmd_wizard)

    c = sub.add_parser("list", help="instancias dadas de alta en este proyecto")
    c.set_defaults(func=cmd_list)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
