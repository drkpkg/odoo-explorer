"""READ-ONLY probes against an Odoo instance.

They collect what the instance knows about itself and the source code cannot
tell you: which modules are installed, which fields and views were added on top,
and what state the records are actually in, with what volume.

  python3 odoo_probe.py -i cliente overview
  python3 odoo_probe.py -i cliente modules --serie 18.0
  python3 odoo_probe.py -i cliente model mrp.production
  python3 odoo_probe.py -i cliente states mrp.production
  python3 odoo_probe.py -i cliente graph mrp.production --depth 1
  python3 odoo_probe.py -i cliente customizations
  python3 odoo_probe.py -i cliente sample sale.order --limit 5
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from odoo_ro import OdooRO, instance_dir  # noqa: E402
import odoo_source  # noqa: E402

# Campos relacionales cuyo destino casi nunca aporta al mapa de un proceso.
NOISE_MODELS = {
    "res.users", "res.company", "res.currency", "res.lang", "ir.attachment",
    "mail.thread", "mail.activity", "mail.message", "mail.followers",
    "ir.ui.view", "ir.model", "ir.model.fields", "ir.attachment",
    "mail.activity.type", "res.groups", "ir.sequence",
}


def _out(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def _safe(odoo, model, wanted):
    """Intersect the requested fields with the ones the model actually has."""
    available = set(odoo.fields_get(model, ["type"]).keys())
    return [f for f in wanted if f in available]


def cmd_overview(a):
    odoo = OdooRO.from_instance(a.instance, a.project)
    data = {"instance": odoo.summary()}
    data["companies"] = odoo.search_read(
        "res.company", [], _safe(odoo, "res.company", ["name", "currency_id", "country_id"]))
    data["users"] = {
        "internos": odoo.count("res.users", [("share", "=", False), ("active", "=", True)]),
        "portal_publico": odoo.count("res.users", [("share", "=", True)]),
    }
    data["languages"] = odoo.search_read("res.lang", [("active", "=", True)], ["code", "name"])
    mods = odoo.search_read(
        "ir.module.module", [("state", "=", "installed")],
        _safe(odoo, "ir.module.module", ["name", "shortdesc", "author", "latest_version"]))
    data["installed_modules_count"] = len(mods)
    data["installed_modules"] = sorted(m["name"] for m in mods)
    d = instance_dir(a.instance, a.project)
    if a.save:
        (d / "profile.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        data["written"] = str(d / "profile.json")
    _out(data)


def cmd_modules(a):
    """Classify the installed modules against the official source of the series."""
    odoo = OdooRO.from_instance(a.instance, a.project)
    serie = a.serie or odoo.server_serie()
    serie, warn = odoo_source.normalize_serie(serie)
    standard = set()
    for base in odoo_source.addons_paths(serie):
        for p in base.iterdir():
            if (p / "__manifest__.py").exists():
                standard.add(p.name)
    mods = odoo.search_read(
        "ir.module.module", [("state", "=", "installed")],
        _safe(odoo, "ir.module.module",
              ["name", "shortdesc", "author", "latest_version", "category_id"]),
        order="name")
    for m in mods:
        m["origin"] = "estandar" if m["name"] in standard else "fuera-de-la-fuente"
    non_std = [m for m in mods if m["origin"] == "fuera-de-la-fuente"]
    _out({
        "serie": serie,
        "warning": warn,
        "source_available": bool(standard),
        "total_installed": len(mods),
        "standard": len(mods) - len(non_std),
        "non_standard": non_std,
        "modules": mods if a.all else None,
        "note": "'fuera-de-la-fuente' = a medida, OCA, o Enterprise (el nightly publico "
                "solo trae Community). El campo author es texto libre y puede estar falseado: "
                "no clasifiques por author.",
    })


def _state_field(fields):
    for candidate in ("state", "status", "stage_id"):
        if candidate in fields:
            return candidate
    return None


def cmd_model(a):
    odoo = OdooRO.from_instance(a.instance, a.project)
    model = a.model
    if not odoo.model_exists(model):
        raise SystemExit("El modelo %r no existe en esta instancia (modulo no instalado?)." % model)
    fg = odoo.fields_get(model, [
        "string", "type", "relation", "required", "readonly", "store",
        "selection", "related", "help", "tracking", "compute"])
    meta = odoo.search_read(
        "ir.model", [("model", "=", model)],
        _safe(odoo, "ir.model", ["name", "model", "modules", "transient", "state"]), limit=1)
    interesting = {}
    for name, f in fg.items():
        if a.all_fields or f.get("required") or f.get("type") in (
                "many2one", "one2many", "many2many", "selection") or name in (
                "name", "state", "company_id", "date", "user_id", "partner_id"):
            interesting[name] = {k: v for k, v in f.items() if v not in (None, False, "")}
    result = {
        "model": model,
        "meta": meta[0] if meta else None,
        "record_count": odoo.count(model, []),
        "field_count": len(fg),
        "fields": interesting,
        "state_field": _state_field(fg),
    }
    sf = result["state_field"]
    if sf and fg[sf].get("type") == "selection":
        result["states"] = fg[sf].get("selection")
        result["state_distribution"] = _distribution(odoo, model, sf)
    result["views"] = odoo.search_read(
        "ir.ui.view", [("model", "=", model), ("active", "=", True)],
        _safe(odoo, "ir.ui.view", ["name", "type", "inherit_id", "priority"]),
        order="type,priority", limit=60)
    result["manual_fields"] = odoo.search_read(
        "ir.model.fields",
        [("model", "=", model), ("state", "=", "manual")],
        _safe(odoo, "ir.model.fields", ["name", "field_description", "ttype", "relation"]))
    _out(result)


def _distribution(odoo, model, field):
    try:
        groups = odoo.read_group(model, [], ["id"], [field], lazy=False)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    out = {}
    for g in groups:
        key = g.get(field)
        if isinstance(key, (list, tuple)):
            key = key[1] if len(key) > 1 else key[0]
        out[str(key)] = g.get("__count") or g.get("%s_count" % field) or 0
    return out


def cmd_states(a):
    odoo = OdooRO.from_instance(a.instance, a.project)
    fg = odoo.fields_get(a.model, ["type", "selection", "string"])
    field = a.field or _state_field(fg)
    if not field:
        raise SystemExit("El modelo %r no tiene campo de estado evidente." % a.model)
    _out({
        "model": a.model, "field": field,
        "label": fg[field].get("string"),
        "selection": fg[field].get("selection"),
        "distribution": _distribution(odoo, a.model, field),
        "total": odoo.count(a.model, []),
    })


def cmd_graph(a):
    """Neighbouring models of a given one. Feeds the model-map diagram."""
    odoo = OdooRO.from_instance(a.instance, a.project)
    seen, edges, frontier = set(), [], [a.model]
    for _depth in range(max(1, a.depth)):
        nxt = []
        for model in frontier:
            if model in seen or model in NOISE_MODELS:
                continue
            seen.add(model)
            try:
                fg = odoo.fields_get(model, ["type", "relation", "string", "required"])
            except Exception:  # noqa: BLE001
                continue
            for name, f in fg.items():
                rel = f.get("relation")
                if not rel or rel in NOISE_MODELS or rel.startswith("ir."):
                    continue
                if a.required_only and f["type"] == "many2one" and not f.get("required"):
                    continue
                edges.append({"from": model, "to": rel, "field": name,
                              "type": f["type"], "label": f.get("string")})
                nxt.append(rel)
        frontier = nxt
    counts = {}
    for m in sorted(seen):
        try:
            counts[m] = odoo.count(m, [])
        except Exception:  # noqa: BLE001
            counts[m] = None
    _out({"root": a.model, "models": sorted(seen), "record_counts": counts,
          "edges": edges[:a.limit], "edge_total": len(edges)})


def cmd_customizations(a):
    odoo = OdooRO.from_instance(a.instance, a.project)
    out = {}
    out["manual_fields"] = odoo.search_read(
        "ir.model.fields", [("state", "=", "manual")],
        _safe(odoo, "ir.model.fields",
              ["model", "name", "field_description", "ttype", "relation"]), limit=300)
    out["server_actions"] = odoo.search_read(
        "ir.actions.server", [],
        _safe(odoo, "ir.actions.server", ["name", "model_id", "state", "usage"]), limit=200)
    for model in ("base.automation", "base.action.rule"):
        if odoo.model_exists(model):
            out["automations"] = odoo.search_read(
                model, [], _safe(odoo, model,
                                 ["name", "model_id", "trigger", "active", "filter_domain"]),
                limit=200)
            break
    out["crons"] = odoo.search_read(
        "ir.cron", [], _safe(odoo, "ir.cron",
                             ["name", "model_id", "interval_type", "active", "nextcall"]),
        limit=200)
    if a.model:
        for key in ("manual_fields", "server_actions", "automations", "crons"):
            rows = out.get(key) or []
            out[key] = [r for r in rows if a.model in json.dumps(r, default=str)]
    _out(out)


def cmd_sample(a):
    odoo = OdooRO.from_instance(a.instance, a.project)
    fields = a.fields.split(",") if a.fields else []
    _out(odoo.search_read(a.model, json.loads(a.domain) if a.domain else [],
                          fields, limit=a.limit, order=a.order or "id desc"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-i", "--instance", required=True)
    p.add_argument("--project")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("overview"); c.add_argument("--save", action="store_true")
    c.set_defaults(func=cmd_overview)

    c = sub.add_parser("modules"); c.add_argument("--serie")
    c.add_argument("--all", action="store_true", help="incluir tambien los estandar")
    c.set_defaults(func=cmd_modules)

    c = sub.add_parser("model"); c.add_argument("model")
    c.add_argument("--all-fields", action="store_true")
    c.set_defaults(func=cmd_model)

    c = sub.add_parser("states"); c.add_argument("model"); c.add_argument("--field")
    c.set_defaults(func=cmd_states)

    c = sub.add_parser("graph"); c.add_argument("model")
    c.add_argument("--depth", type=int, default=1)
    c.add_argument("--limit", type=int, default=120)
    c.add_argument("--required-only", action="store_true")
    c.set_defaults(func=cmd_graph)

    c = sub.add_parser("customizations"); c.add_argument("--model")
    c.set_defaults(func=cmd_customizations)

    c = sub.add_parser("sample"); c.add_argument("model")
    c.add_argument("--domain"); c.add_argument("--fields")
    c.add_argument("--limit", type=int, default=5); c.add_argument("--order")
    c.set_defaults(func=cmd_sample)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
