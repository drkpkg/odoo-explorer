"""Strictly READ-ONLY Odoo XML-RPC client.

Every call goes through a guard that only allows read methods. Any write attempt
(create/write/unlink/button_*/...) raises ReadOnlyViolation BEFORE it touches the
network.

Do not extend ALLOWED_METHODS. It is the only code-level guarantee that this tool
cannot modify a customer's instance.

As a library:
    from odoo_ro import OdooRO, resolve_instance
    odoo = OdooRO.from_instance("mi-cliente")
    odoo.search_read("res.partner", [("customer_rank", ">", 0)], ["name"], limit=5)

As a CLI (one-off queries, JSON output):
    python3 odoo_ro.py -i mi-cliente call res.partner search_count --args '[[]]'
    python3 odoo_ro.py -i mi-cliente search-read sale.order --domain '[["state","=","sale"]]' \
        --fields name,partner_id,amount_total --limit 10
    python3 odoo_ro.py -i mi-cliente read-group stock.picking \
        --domain '[]' --fields '["id"]' --groupby '["state"]'
"""
import argparse
import http.client
import json
import os
import pathlib
import sys
import xmlrpc.client

# --- Guardia de solo lectura -------------------------------------------------
ALLOWED_METHODS = frozenset({
    "search", "search_read", "search_count", "read", "read_group",
    "fields_get", "fields_view_get", "load_views", "get_views",
    "name_get", "name_search", "default_get", "get_metadata",
    "check_access_rights", "get_external_id", "get_xml_id",
    "search_fetch", "web_search_read", "web_read_group", "formatted_read_group",
})

# Prefijos que delatan una escritura aunque el nombre sea creativo.
FORBIDDEN_PREFIXES = (
    "create", "write", "unlink", "copy", "import", "load_", "install",
    "upgrade", "button_", "action_", "set_", "toggle_", "update", "confirm",
    "cancel", "validate", "post", "send", "process", "apply", "do_",
    "_write", "_create", "_unlink",
)


class ReadOnlyViolation(RuntimeError):
    pass


def assert_read_only(model, method):
    """Strict allowlist. Anything not listed is blocked."""
    if method in ALLOWED_METHODS:
        return
    raise ReadOnlyViolation(
        "BLOQUEADO: %s.%s no esta en la lista de metodos de lectura. "
        "odoo-explorer es estrictamente de solo lectura; no se amplia la lista "
        "blanca. Si de verdad hace falta una escritura, pidela al usuario y que "
        "la ejecute el mismo fuera de esta herramienta." % (model, method)
    )


# --- Localizacion del proyecto y de la instancia -----------------------------
def project_root(explicit=None):
    """Working directory that holds instances/. Defaults to the cwd."""
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    env = os.environ.get("ODOO_EXPLORER_HOME")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    return pathlib.Path.cwd().resolve()


def instance_dir(slug, root=None):
    return project_root(root) / "instances" / slug


def list_instances(root=None):
    base = project_root(root) / "instances"
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir()
        if p.is_dir() and (p / "instance.json").exists()
    )


def read_env_file(path):
    """Read a simple .env file. Returns a dict, or {} when it does not exist."""
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def resolve_instance(slug, root=None):
    """Return (config, directory). The password comes from .env or ODOO_PASSWORD.

    Only ODOO_-prefixed environment overrides are honoured: bare shell variables
    (USER, HOST, PWD) would otherwise clobber the stored configuration.
    """
    d = instance_dir(slug, root)
    conf_path = d / "instance.json"
    if not conf_path.exists():
        raise SystemExit(
            "No existe la instancia %r en %s.\n"
            "Instancias disponibles: %s\n"
            "Crea una con: python3 odoo_connect.py --instance %s --host ... --db ... --user ..."
            % (slug, conf_path, ", ".join(list_instances(root)) or "(ninguna)", slug)
        )
    conf = json.loads(conf_path.read_text(encoding="utf-8"))
    env = read_env_file(d / ".env")
    conf["password"] = os.environ.get("ODOO_PASSWORD") or env.get("PASSWORD") or ""
    for key in ("host", "port", "protocol", "db", "user"):
        override = os.environ.get("ODOO_" + key.upper())
        if override:
            conf[key] = override
    if not conf["password"]:
        raise SystemExit(
            "Falta la contrasena de %r. Guardala por STDIN, nunca en la linea de "
            "comandos:\n"
            "  printf '%%s' 'la-clave' | python3 odoo_connect.py set-password "
            "--instance %s\n"
            "Queda en %s con permisos 600." % (slug, slug, d / ".env")
        )
    return conf, d


# --- Transporte con timeout --------------------------------------------------
class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout, use_https=False, **kw):
        super().__init__(**kw)
        self._timeout = timeout
        self._use_https = use_https

    def make_connection(self, host):
        if self._connection and host == self._connection[0]:
            return self._connection[1]
        chost, self._extra_headers, x509 = self.get_host_info(host)
        if self._use_https:
            import ssl
            conn = http.client.HTTPSConnection(
                chost, None, timeout=self._timeout,
                context=ssl._create_unverified_context() if os.environ.get(
                    "ODOO_INSECURE_TLS") else None,
                **(x509 or {}))
        else:
            conn = http.client.HTTPConnection(chost, timeout=self._timeout)
        self._connection = host, conn
        return conn


# --- Cliente -----------------------------------------------------------------
class OdooRO:
    """Read-only connection to an Odoo database over XML-RPC."""

    def __init__(self, host, user, password, db=None, port=None,
                 protocol="http", timeout=60, slug=None, directory=None):
        self.host = host
        self.protocol = (protocol or "http").lower()
        self.port = str(port) if port else ("443" if self.protocol == "https" else "8069")
        self.db = db
        self.user = user
        self.password = password
        self.slug = slug
        self.directory = pathlib.Path(directory) if directory else None
        self.timeout = timeout
        self.uid = None
        self._version = None
        default_port = self.protocol == "https" and self.port == "443"
        self.url = "%s://%s%s" % (
            self.protocol, host, "" if default_port else ":" + self.port)
        https = self.protocol == "https"
        self._common = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/common", allow_none=True,
            transport=_TimeoutTransport(timeout, https))
        self._models = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/object", allow_none=True,
            transport=_TimeoutTransport(timeout, https))
        self._db = xmlrpc.client.ServerProxy(
            self.url + "/xmlrpc/2/db", allow_none=True,
            transport=_TimeoutTransport(timeout, https))

    @classmethod
    def from_instance(cls, slug, root=None, connect=True):
        conf, d = resolve_instance(slug, root)
        odoo = cls(
            host=conf["host"], user=conf["user"], password=conf["password"],
            db=conf.get("db"), port=conf.get("port"),
            protocol=conf.get("protocol", "http"),
            timeout=int(conf.get("timeout") or 60),
            slug=slug, directory=d,
        )
        if connect:
            odoo.authenticate()
        return odoo

    # -- sesion ---------------------------------------------------------------
    def version(self):
        if self._version is None:
            self._version = self._common.version()
        return self._version

    def server_serie(self):
        """'18.0', derived from server_serie or from server_version ('18.0+e')."""
        v = self.version()
        serie = v.get("server_serie")
        if serie:
            return str(serie)
        raw = str(v.get("server_version", ""))
        return raw.split("+")[0].split("-")[0] or ""

    def is_enterprise(self):
        v = self.version()
        raw = str(v.get("server_version", ""))
        if "+e" in raw:
            return True
        info = v.get("server_version_info") or []
        return any(str(part) == "e" for part in info)

    def list_databases(self):
        """May be disabled server-side (list_db = False). Returns None when it is."""
        try:
            return self._db.list()
        except Exception:
            return None

    def authenticate(self):
        if not self.db:
            raise SystemExit(
                "Falta la base de datos. Pasa --db, o usa 'odoo_connect.py --list-dbs' "
                "para ver cuales expone el servidor.")
        self.uid = self._common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise SystemExit(
                "Autenticacion fallida en la base %r con el usuario %r." % (self.db, self.user))
        return self.uid

    # -- llamada base ---------------------------------------------------------
    def call(self, model, method, *args, **kwargs):
        assert_read_only(model, method)
        if self.uid is None:
            self.authenticate()
        return self._models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs)

    # -- azucar ---------------------------------------------------------------
    def search_read(self, model, domain=None, fields=None, **kw):
        return self.call(model, "search_read", domain or [], fields or [], **kw)

    def search(self, model, domain=None, **kw):
        return self.call(model, "search", domain or [], **kw)

    def read(self, model, ids, fields=None, **kw):
        return self.call(model, "read", ids, fields or [], **kw)

    def count(self, model, domain=None, **kw):
        return self.call(model, "search_count", domain or [], **kw)

    def read_group(self, model, domain, fields, groupby, **kw):
        return self.call(model, "read_group", domain or [], fields, groupby, **kw)

    def fields_get(self, model, attributes=None):
        kw = {"attributes": attributes} if attributes else {}
        return self.call(model, "fields_get", [], **kw)

    def model_exists(self, model):
        return bool(self.call("ir.model", "search_count", [("model", "=", model)]))

    def summary(self):
        return {
            "instance": self.slug,
            "url": self.url,
            "db": self.db,
            "user": self.user,
            "uid": self.uid,
            "serie": self.server_serie(),
            "edition": "enterprise" if self.is_enterprise() else "community",
            "server_version": self.version().get("server_version"),
        }


# --- CLI ---------------------------------------------------------------------
def _json_arg(raw, default):
    if raw is None:
        return default
    return json.loads(raw)


def _out(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Consultas de SOLO LECTURA contra una instancia Odoo.")
    p.add_argument("-i", "--instance", required=True, help="slug de instances/<slug>")
    p.add_argument("--project", help="raiz del proyecto (por defecto, el cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("call", help="llamada cruda a un metodo de lectura")
    c.add_argument("model")
    c.add_argument("method")
    c.add_argument("--args", help="lista JSON de argumentos posicionales")
    c.add_argument("--kwargs", help="objeto JSON de argumentos con nombre")

    c = sub.add_parser("search-read")
    c.add_argument("model")
    c.add_argument("--domain", help="dominio JSON (por defecto [])")
    c.add_argument("--fields", help="lista de campos separada por comas")
    c.add_argument("--limit", type=int, default=80)
    c.add_argument("--offset", type=int, default=0)
    c.add_argument("--order")

    c = sub.add_parser("count")
    c.add_argument("model")
    c.add_argument("--domain")

    c = sub.add_parser("read-group")
    c.add_argument("model")
    c.add_argument("--domain")
    c.add_argument("--fields", default='["id"]', help="lista JSON de campos agregados")
    c.add_argument("--groupby", required=True, help="lista JSON de agrupadores")
    c.add_argument("--lazy", action="store_true")

    c = sub.add_parser("fields")
    c.add_argument("model")

    sub.add_parser("whoami", help="version, edicion y usuario autenticado")

    a = p.parse_args(argv)
    odoo = OdooRO.from_instance(a.instance, a.project, connect=a.cmd != "whoami")

    if a.cmd == "whoami":
        odoo.authenticate()
        _out(odoo.summary())
    elif a.cmd == "call":
        _out(odoo.call(a.model, a.method,
                       *_json_arg(a.args, []), **_json_arg(a.kwargs, {})))
    elif a.cmd == "search-read":
        kw = {"limit": a.limit, "offset": a.offset}
        if a.order:
            kw["order"] = a.order
        _out(odoo.search_read(
            a.model, _json_arg(a.domain, []),
            a.fields.split(",") if a.fields else [], **kw))
    elif a.cmd == "count":
        _out({"model": a.model, "count": odoo.count(a.model, _json_arg(a.domain, []))})
    elif a.cmd == "read-group":
        _out(odoo.read_group(
            a.model, _json_arg(a.domain, []), _json_arg(a.fields, ["id"]),
            _json_arg(a.groupby, []), lazy=a.lazy))
    elif a.cmd == "fields":
        _out(odoo.fields_get(a.model, [
            "string", "type", "relation", "required", "readonly", "store",
            "selection", "related", "help", "states", "tracking"]))


if __name__ == "__main__":
    try:
        main()
    except ReadOnlyViolation as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
