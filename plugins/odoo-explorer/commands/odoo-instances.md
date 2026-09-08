---
description: Lista las instancias Odoo dadas de alta, sus versiones y los procesos ya documentados
---

Ejecuta y resume en una tabla:

```bash
export ODOO_EX="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(find ~/.claude/plugins -type f -name odoo_ro.py -path '*odoo-explorer*' 2>/dev/null | head -1)")")}"
python3 "$ODOO_EX/scripts/odoo_connect.py" list
python3 "$ODOO_EX/scripts/odoo_source.py" list
```

Muestra por instancia: etiqueta, servidor, base, version y edicion, si tiene contrasena
guardada, y que procesos tiene ya documentados. Indica tambien que series de codigo fuente
estan cacheadas y cuales faltarian.
