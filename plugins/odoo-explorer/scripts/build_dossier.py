"""Render a process dossier to interactive HTML, always the same shape.

The structure is NOT improvised on every request: Claude fills in a JSON with a
closed schema (dossier.json) and this script compiles it into index.html. Same
sections, same order, same slots for the five Archify diagrams. A section with no
data renders empty and says why; it never disappears.

  python3 build_dossier.py validate instances/cliente/processes/manufactura/dossier.json
  python3 build_dossier.py render   instances/cliente/processes/manufactura/dossier.json
  python3 build_dossier.py export   instances/cliente/processes/manufactura/dossier.json
  python3 build_dossier.py index    --instance cliente
  python3 build_dossier.py scaffold --instance cliente --process manufactura \
      --title "Proceso de manufactura"
"""
import argparse
import datetime
import html
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from odoo_ro import instance_dir, list_instances, project_root  # noqa: E402

SCHEMA = "odoo-explorer/dossier@1"

# Los cinco huecos de diagrama. Orden y significado fijos.
SLOTS = [
    ("map", "architecture", "Mapa de modelos",
     "Que modelos participan y como se enlazan."),
    ("lifecycle", "lifecycle", "Ciclo de vida del documento",
     "Estados por los que pasa el documento principal y que los hace avanzar."),
    ("flow", "workflow", "Flujo extremo a extremo",
     "El proceso completo por carriles, con sus ramas y excepciones."),
    ("triggers", "sequence", "Que ejecuta cada accion",
     "La cadena de llamadas reales del codigo fuente al pulsar cada boton."),
    ("data", "dataflow", "Movimiento de datos",
     "Que registros se crean, se mueven y se contabilizan en cada paso."),
]

REQUIRED = ["process", "instance", "resumen", "scope", "steps", "models", "lifecycle",
            "key_fields", "config", "this_instance", "evidence"]

# Secciones que solo interesan a un perfil tecnico. Se ocultan en la vista Resumen.
TECH_SECTIONS = ("s6", "s8", "s11")


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def _list(items, empty="Sin datos recogidos."):
    items = items or []
    if not items:
        return '<p class="empty">%s</p>' % e(empty)
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % e(i) for i in items)


def _table(rows, columns, empty="Sin datos recogidos."):
    rows = rows or []
    if not rows:
        return '<p class="empty">%s</p>' % e(empty)
    head = "".join("<th>%s</th>" % e(label) for _key, label in columns)
    body = []
    for row in rows:
        cells = []
        for key, _label in columns:
            val = row.get(key)
            if isinstance(val, bool):
                val = "si" if val else "no"
            elif isinstance(val, (list, tuple)):
                val = ", ".join(str(v) for v in val)
            cells.append("<td>%s</td>" % e(val))
        body.append("<tr>%s</tr>" % "".join(cells))
    return ('<div class="scroll"><table><thead><tr>%s</tr></thead>'
            "<tbody>%s</tbody></table></div>" % (head, "".join(body)))


def _diagram(dossier, slot_key, title, caption, base_dir, embed=False):
    found = None
    for d in dossier.get("diagrams") or []:
        if d.get("slot") == slot_key:
            found = d
            break
    if not found:
        return ('<div class="diagram missing"><p class="empty">Diagrama no generado. '
                "Genera el JSON del tipo <code>%s</code> y compilalo con "
                "<code>archify deliver</code> en <code>diagrams/</code>.</p></div>"
                % e(dict(SLOTS_BY_KEY)[slot_key]))
    rel = found.get("file", "")
    exists = (base_dir / rel).exists() if rel else False
    note = e(found.get("caption") or caption)
    if not exists:
        return ('<div class="diagram missing"><p class="empty">Falta el fichero '
                "<code>%s</code>. Compilalo con <code>archify deliver</code>.</p></div>" % e(rel))
    if embed:
        crudo = (base_dir / rel).read_text(encoding="utf-8")
        return (
            '<figure class="diagram">'
            '<iframe srcdoc="%s" title="%s" loading="lazy"></iframe>'
            "<figcaption>%s</figcaption></figure>"
            % (e(crudo), e(title), note)
        )
    return (
        '<figure class="diagram">'
        '<iframe src="%s" title="%s" loading="lazy"></iframe>'
        '<figcaption>%s <a class="pop" href="%s" target="_blank" rel="noopener">'
        "abrir a pantalla completa &#8599;</a></figcaption></figure>"
        % (e(rel), e(title), note, e(rel))
    )


SLOTS_BY_KEY = [(k, t) for k, t, _l, _c in SLOTS]

CSS = """
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1b1a18;--muted:#6b6660;--line:#e3ded7;
--accent:#7a3e12;--accent-soft:#f3ece3;--warn:#8a5a00;--ok:#2f6b3a;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#131211;--panel:#1b1a18;--ink:#eae6e0;
--muted:#a19a91;--line:#332f2b;--accent:#e0a06a;--accent-soft:#26221e;
--warn:#d9a441;--ok:#7fbf8a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
line-height:1.55;font-size:15px}
.wrap{max-width:1100px;margin:0 auto;padding:0 24px 96px}
header.top{border-bottom:1px solid var(--line);background:var(--panel);
padding:32px 0 24px;margin-bottom:32px}
header.top .wrap{padding-bottom:0}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;
color:var(--accent);font-weight:600;margin:0 0 6px}
h1{font-size:31px;line-height:1.15;margin:0 0 14px;letter-spacing:-.02em}
h2{font-size:20px;margin:0 0 4px;letter-spacing:-.01em}
h3{font-size:15px;margin:22px 0 6px}
.sub{color:var(--muted);margin:0 0 18px;max-width:70ch}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:0}
.fact{background:var(--accent-soft);border:1px solid var(--line);border-radius:999px;
padding:4px 12px;font-size:12.5px;color:var(--muted)}
.fact b{color:var(--ink);font-weight:600}
.ro{background:transparent;border-color:var(--ok);color:var(--ok);font-weight:600}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:24px 26px;margin:0 0 20px}
section>.hint{color:var(--muted);font-size:13.5px;margin:0 0 16px;max-width:72ch}
.n{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;
border-radius:6px;background:var(--accent-soft);color:var(--accent);font-size:12px;
font-weight:700;margin-right:9px;font-family:var(--mono)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 12px 7px 0;border-bottom:1px solid var(--line);
vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:11.5px;letter-spacing:.06em;
text-transform:uppercase}
.scroll{overflow-x:auto}
code{font-family:var(--mono);font-size:12.5px;background:var(--accent-soft);
padding:1px 5px;border-radius:4px}
ul{margin:8px 0;padding-left:20px}li{margin:3px 0}
.empty{color:var(--muted);font-style:italic;font-size:13.5px}
.diagram{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;
background:var(--bg)}
.diagram iframe{width:100%;height:620px;border:0;display:block;background:var(--bg)}
.diagram.missing{padding:22px;border-style:dashed}
figcaption{padding:10px 14px;font-size:12.5px;color:var(--muted);
border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:16px}
a{color:var(--accent)}
.step{border-left:2px solid var(--line);padding:0 0 4px 18px;margin:0 0 22px}
.step:last-child{margin-bottom:0}
.step h3{margin:0 0 2px;font-size:15.5px}
.step .meta{font-size:12.5px;color:var(--muted);margin:0 0 8px}
.step .meta span{margin-right:14px}
.arrow{font-family:var(--mono);color:var(--accent)}
.ev{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
footer{color:var(--muted);font-size:12.5px;text-align:center;padding-top:8px}
.summary{background:var(--accent-soft);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:12px;padding:24px 26px;margin:0 0 20px}
.summary h2{margin:0 0 10px}
.summary .lead{font-size:17px;line-height:1.5;margin:0 0 14px;max-width:68ch}
.summary ul{margin:6px 0 0}
.summary .k{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
margin:16px 0 0;font-weight:600}
.viewsw{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;
margin-top:14px;background:var(--panel)}
.viewsw button{border:0;background:transparent;color:var(--muted);font:inherit;font-size:12.5px;
padding:5px 15px;cursor:pointer}
.viewsw button[aria-pressed="true"]{background:var(--accent);color:var(--panel);font-weight:600}
body[data-view="resumen"] [data-tech="1"]{display:none}
body[data-view="resumen"] .ev{display:none}
body[data-view="resumen"] .techonly{display:none}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.card{border:1px solid var(--line);border-radius:9px;padding:14px 16px}
.card .k{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.card .v{font-size:22px;font-weight:600;margin-top:2px;letter-spacing:-.01em}
"""


def render(dossier, base_dir, embed=False):
    proc = dossier.get("process") or {}
    inst = dossier.get("instance") or {}
    scope = dossier.get("scope") or {}
    life = dossier.get("lifecycle") or {}
    ti = dossier.get("this_instance") or {}
    ev = dossier.get("evidence") or {}

    facts = [
        ("Instancia", inst.get("label") or inst.get("slug")),
        ("Base", inst.get("db")),
        ("Version", "%s %s" % (inst.get("serie") or "?", inst.get("edition") or "")),
        ("Modulos", ", ".join(scope.get("modules") or []) or "-"),
        ("Analisis", dossier.get("generated_at")),
    ]
    facts_html = "".join(
        '<span class="fact"><b>%s</b> %s</span>' % (e(k), e(v)) for k, v in facts if v)
    facts_html += '<span class="fact ro">solo lectura</span>'

    res = dossier.get("resumen") or {}
    resumen_html = (
        '<div class="summary"><h2>En resumen</h2>'
        '<p class="lead">%s</p>%s'
        '<p class="k">Que significa para el negocio</p>%s</div>'
        % (e(res.get("en_una_frase") or "Resumen no redactado."),
           _list(res.get("puntos"), "Sin puntos clave redactados."),
           _list(res.get("implicaciones"), "Sin implicaciones redactadas."))
    )

    steps_html = []
    for i, s in enumerate(dossier.get("steps") or [], 1):
        meta = []
        if s.get("actor"):
            meta.append("<span>%s</span>" % e(s["actor"]))
        if s.get("ui"):
            meta.append("<span>%s</span>" % e(s["ui"]))
        if s.get("model"):
            meta.append("<span><code>%s</code></span>" % e(s["model"]))
        if s.get("state_from") or s.get("state_to"):
            meta.append('<span class="arrow">%s &rarr; %s</span>'
                        % (e(s.get("state_from") or "-"), e(s.get("state_to") or "-")))
        body = []
        if s.get("trigger"):
            body.append("<p>Se dispara con: %s</p>" % e(s["trigger"]))
        if s.get("what_happens"):
            body.append("<p><b>Que ocurre por dentro</b></p>" + _list(s["what_happens"]))
        if s.get("creates"):
            body.append("<p><b>Que registros aparecen o cambian</b></p>" + _list(s["creates"]))
        refs = [r.get("ref") if isinstance(r, dict) else r for r in (s.get("evidence") or [])]
        if refs:
            body.append('<p class="ev">%s</p>' % e(" &middot; ".join(str(r) for r in refs)))
        steps_html.append(
            '<div class="step"><h3><span class="n">%d</span>%s</h3>'
            '<p class="meta">%s</p>%s</div>'
            % (i, e(s.get("title") or "(sin titulo)"), "".join(meta), "".join(body)))
    steps_block = "".join(steps_html) or '<p class="empty">Sin pasos documentados.</p>'

    state_rows = life.get("states") or []
    volumes = ti.get("volumes") or []
    vol_html = "".join(
        '<div class="card"><div class="k">%s</div><div class="v">%s</div></div>'
        % (e(v.get("label")), e(v.get("value"))) for v in volumes)

    sections = [
        ("1", "Alcance", "Que cubre este dossier y que deliberadamente deja fuera.",
         _list(scope.get("covers"), "Alcance no declarado.")
         + "<h3>Fuera de alcance</h3>" + _list(scope.get("excludes"), "Nada excluido explicitamente.")),

        ("2", "Quien interviene", "Los roles que tocan el proceso y en que momento.",
         _table(dossier.get("actors"), [("role", "Rol"), ("does", "Que hace"),
                                        ("group", "Grupo de acceso")])),

        ("3", "Mapa de modelos", "Los modelos implicados y como se enlazan entre si.",
         _diagram(dossier, "map", "Mapa de modelos", SLOTS[0][3], base_dir, embed)
         + _table(dossier.get("models"),
                  [("model", "Modelo"), ("role", "Papel en el proceso"),
                   ("module", "Modulo"), ("count", "Registros"), ("custom", "A medida")])),

        ("4", "Ciclo de vida del documento",
         "Los estados reales del documento principal, con cuantos registros hay hoy en cada uno.",
         _diagram(dossier, "lifecycle", "Ciclo de vida", SLOTS[1][3], base_dir, embed)
         + _table(state_rows, [("key", "Estado"), ("label", "Etiqueta"),
                               ("count", "Registros"), ("means", "Que significa")])),

        ("5", "El proceso, paso a paso",
         "El recorrido completo. Cada paso dice quien lo hace, desde donde, que dispara "
         "y que ocurre por dentro.",
         _diagram(dossier, "flow", "Flujo extremo a extremo", SLOTS[2][3], base_dir, embed)
         + steps_block),

        ("6", "Que ejecuta cada accion",
         "La traza tecnica: la cadena de llamadas del codigo fuente detras de cada boton.",
         _diagram(dossier, "triggers", "Cadena de llamadas", SLOTS[3][3], base_dir, embed)
         + _table(dossier.get("triggers"),
                  [("ui", "Boton o accion"), ("method", "Metodo"),
                   ("effect", "Efecto"), ("source", "Fuente")])),

        ("7", "Movimiento de datos",
         "Que registros se crean, que se mueve y que llega a contabilidad o a stock.",
         _diagram(dossier, "data", "Movimiento de datos", SLOTS[4][3], base_dir, embed)),

        ("8", "Campos clave",
         "Los campos que de verdad gobiernan el comportamiento, no el listado completo.",
         _table(dossier.get("key_fields"),
                [("model", "Modelo"), ("field", "Campo"), ("label", "Etiqueta"),
                 ("type", "Tipo"), ("why", "Por que importa"), ("custom", "A medida")])),

        ("9", "Configuracion que cambia el comportamiento",
         "Ajustes que hacen que este proceso se comporte distinto de la documentacion generica.",
         _table(dossier.get("config"),
                [("where", "Donde"), ("option", "Opcion"), ("value", "Valor aqui"),
                 ("effect", "Efecto sobre el proceso")])),

        ("10", "Esta instancia en concreto",
         "Lo que separa a esta implantacion del Odoo de manual.",
         (('<div class="grid">%s</div>' % vol_html) if vol_html else "")
         + "<h3>Hallazgos</h3>" + _list(ti.get("findings"))
         + "<h3>Desviaciones del estandar</h3>"
         + _list(ti.get("deviations"), "Ninguna detectada.")),

        ("11", "Evidencia",
         "De donde sale cada afirmacion: fichero y linea del codigo fuente, o la llamada "
         "de lectura ejecutada contra la instancia.",
         "<h3>Codigo fuente</h3>" + _list(ev.get("source_refs"))
         + "<h3>Consultas ejecutadas (solo lectura)</h3>" + _list(ev.get("rpc_calls"))
         + "<h3>Preguntas abiertas</h3>"
         + _list(dossier.get("open_questions"), "Ninguna pendiente.")),
    ]

    body = "".join(
        '<section id="s%s"><h2><span class="n">%s</span>%s</h2>'
        '<p class="hint">%s</p>%s</section>' % (n, n, e(title), e(hint), content)
        for n, title, hint, content in sections)
    for sid in TECH_SECTIONS:
        body = body.replace('<section id="%s">' % sid,
                            '<section id="%s" data-tech="1">' % sid)

    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s &middot; %(inst)s</title>
<style>%(css)s</style></head><body>
<header class="top"><div class="wrap">
<p class="kicker">Dossier de proceso Odoo</p>
<h1>%(title)s</h1>
<p class="sub">%(question)s</p>
<div class="facts">%(facts)s</div>
<div class="viewsw" role="group" aria-label="Nivel de detalle">
<button type="button" data-v="resumen" aria-pressed="false">Resumen</button>
<button type="button" data-v="completa" aria-pressed="true">Completa</button>
</div>
</div></header>
<div class="wrap">%(resumen)s%(body)s
<footer>Generado por odoo-explorer desde el codigo fuente de Odoo %(serie)s y consultas
de solo lectura a %(url)s. Diagramas: Archify.</footer>
</div>
<script>
(function () {
  var KEY = "odoo-explorer:vista";
  var botones = document.querySelectorAll(".viewsw button");
  function aplicar(v) {
    document.body.dataset.view = v;
    botones.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.v === v));
    });
    try { localStorage.setItem(KEY, v); } catch (err) { /* modo privado */ }
  }
  botones.forEach(function (b) {
    b.addEventListener("click", function () { aplicar(b.dataset.v); });
  });
  var guardada = null;
  try { guardada = localStorage.getItem(KEY); } catch (err) { /* sin almacenamiento */ }
  aplicar(guardada === "resumen" ? "resumen" : "completa");
})();
</script>
</body></html>""" % {
        "title": e(proc.get("title") or proc.get("slug")),
        "inst": e(inst.get("label") or inst.get("slug")),
        "question": e(proc.get("question") or "Recorrido del proceso de punta a punta."),
        "facts": facts_html, "css": CSS, "body": body, "resumen": resumen_html,
        "serie": e(inst.get("serie")), "url": e(inst.get("url")),
    }


def cmd_validate(a):
    path = pathlib.Path(a.dossier)
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if data.get("schema") != SCHEMA:
        problems.append("falta o no coincide 'schema' (debe ser %r)" % SCHEMA)
    for key in REQUIRED:
        if key not in data:
            problems.append("falta la clave obligatoria %r" % key)
    slots = {d.get("slot") for d in (data.get("diagrams") or [])}
    missing_slots = [k for k, _t, _l, _c in SLOTS if k not in slots]
    base = path.parent
    missing_files = [d.get("file") for d in (data.get("diagrams") or [])
                     if d.get("file") and not (base / d["file"]).exists()]
    _out({"ok": not problems, "problems": problems,
          "diagram_slots_missing": missing_slots,
          "diagram_files_missing": missing_files,
          "steps": len(data.get("steps") or [])})
    if problems:
        raise SystemExit(1)


def cmd_render(a):
    path = pathlib.Path(a.dossier).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("generated_at",
                    datetime.datetime.now().isoformat(timespec="minutes"))
    out = path.parent / "index.html"
    out.write_text(render(data, path.parent), encoding="utf-8")
    _out({"written": str(out), "open": "file://%s" % out,
          "diagrams": [d.get("file") for d in (data.get("diagrams") or [])]})


def cmd_export(a):
    """One single HTML file with the diagrams inlined, ready to send or share."""
    path = pathlib.Path(a.dossier).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("generated_at",
                    datetime.datetime.now().isoformat(timespec="minutes"))
    nombre = (data.get("process") or {}).get("slug") or path.parent.name
    inst = (data.get("instance") or {}).get("slug") or "instancia"
    out = pathlib.Path(a.output) if a.output else path.parent / (
        "%s-%s-completo.html" % (inst, nombre))
    out.write_text(render(data, path.parent, embed=True), encoding="utf-8")
    mb = out.stat().st_size / 1e6
    _out({
        "written": str(out),
        "open": "file://%s" % out,
        "size_mb": round(mb, 1),
        "self_contained": True,
        "aviso": ("Pesa %.1f MB: puede ser demasiado para un correo. Comprimelo o "
                  "compartelo por enlace." % mb) if mb > 8 else None,
        "note": "Un solo fichero, con los diagramas dentro. Se abre con doble clic, "
                "sin internet y sin instalar nada.",
    })


def cmd_scaffold(a):
    d = instance_dir(a.instance, a.project) / "processes" / a.process
    (d / "diagrams").mkdir(parents=True, exist_ok=True)
    conf_path = instance_dir(a.instance, a.project) / "instance.json"
    inst = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.exists() else {}
    skeleton = {
        "schema": SCHEMA,
        "process": {"slug": a.process, "title": a.title or a.process,
                    "question": a.question or ""},
        "instance": {"slug": a.instance, "label": inst.get("label"),
                     "url": "%s://%s" % (inst.get("protocol", "http"), inst.get("host", "")),
                     "db": inst.get("db"), "serie": inst.get("serie"),
                     "edition": inst.get("edition")},
        "generated_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "resumen": {"en_una_frase": "", "puntos": [], "implicaciones": []},
        "scope": {"covers": [], "excludes": [], "modules": []},
        "actors": [], "models": [],
        "lifecycle": {"model": "", "field": "state", "states": []},
        "steps": [], "triggers": [], "key_fields": [], "config": [],
        "this_instance": {"volumes": [], "findings": [], "deviations": []},
        "diagrams": [
            {"slot": k, "type": t, "title": label,
             "file": "diagrams/%02d-%s.%s.html" % (i, k, t), "caption": cap}
            for i, (k, t, label, cap) in enumerate(SLOTS, 1)
        ],
        "evidence": {"source_refs": [], "rpc_calls": []},
        "open_questions": [],
    }
    out = d / "dossier.json"
    if out.exists() and not a.force:
        raise SystemExit("Ya existe %s (usa --force para sobrescribir)." % out)
    out.write_text(json.dumps(skeleton, indent=2, ensure_ascii=False), encoding="utf-8")
    _out({"written": str(out), "diagrams_dir": str(d / "diagrams"),
          "slots": [k for k, _t, _l, _c in SLOTS]})


def cmd_index(a):
    d = instance_dir(a.instance, a.project)
    conf = json.loads((d / "instance.json").read_text(encoding="utf-8"))
    procs = []
    pdir = d / "processes"
    if pdir.is_dir():
        for p in sorted(pdir.iterdir()):
            dj = p / "dossier.json"
            if not dj.exists():
                continue
            data = json.loads(dj.read_text(encoding="utf-8"))
            procs.append({
                "slug": p.name,
                "title": (data.get("process") or {}).get("title") or p.name,
                "question": (data.get("process") or {}).get("question") or "",
                "modules": ", ".join((data.get("scope") or {}).get("modules") or []),
                "steps": len(data.get("steps") or []),
                "generated_at": data.get("generated_at"),
                "href": "processes/%s/index.html" % p.name,
                "built": (p / "index.html").exists(),
            })
    cards = "".join(
        '<a class="proc" href="%s"><h3>%s</h3><p>%s</p>'
        '<p class="meta">%s pasos &middot; %s &middot; %s</p></a>'
        % (e(x["href"]), e(x["title"]), e(x["question"]), e(x["steps"]),
           e(x["modules"] or "-"), e(x["generated_at"]))
        for x in procs) or '<p class="empty">Todavia no hay ningun proceso documentado.</p>'
    page = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(label)s &middot; procesos Odoo</title><style>%(css)s
.proc{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);
border-radius:10px;padding:18px 20px;margin-bottom:12px;background:var(--panel)}
.proc:hover{border-color:var(--accent)}
.proc h3{margin:0 0 4px;font-size:17px}
.proc p{margin:0;color:var(--muted);font-size:13.5px}
.proc .meta{font-family:var(--mono);font-size:11.5px;margin-top:8px}
</style></head><body>
<header class="top"><div class="wrap">
<p class="kicker">odoo-explorer</p><h1>%(label)s</h1>
<p class="sub">Procesos documentados de esta instancia. Todo el analisis se hizo en
solo lectura.</p>
<div class="facts"><span class="fact"><b>Base</b> %(db)s</span>
<span class="fact"><b>Servidor</b> %(url)s</span>
<span class="fact"><b>Version</b> %(serie)s %(edition)s</span>
<span class="fact ro">solo lectura</span></div>
</div></header><div class="wrap">%(cards)s</div></body></html>""" % {
        "label": e(conf.get("label") or conf.get("slug")), "css": CSS,
        "db": e(conf.get("db")),
        "url": e("%s://%s" % (conf.get("protocol", "http"), conf.get("host", ""))),
        "serie": e(conf.get("serie")), "edition": e(conf.get("edition")),
        "cards": cards,
    }
    out = d / "index.html"
    out.write_text(page, encoding="utf-8")
    _out({"written": str(out), "open": "file://%s" % out, "processes": procs})


def _out(data):
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write("\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("validate"); c.add_argument("dossier"); c.set_defaults(func=cmd_validate)
    c = sub.add_parser("render"); c.add_argument("dossier"); c.set_defaults(func=cmd_render)

    c = sub.add_parser("export", help="un solo HTML autocontenido, para compartir")
    c.add_argument("dossier"); c.add_argument("--output")
    c.set_defaults(func=cmd_export)

    c = sub.add_parser("scaffold")
    c.add_argument("--instance", required=True); c.add_argument("--process", required=True)
    c.add_argument("--title"); c.add_argument("--question")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_scaffold)

    c = sub.add_parser("index"); c.add_argument("--instance", required=True)
    c.set_defaults(func=cmd_index)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
