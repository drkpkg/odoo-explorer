---
name: odoo-report
description: Debe usarse cuando el usuario pide datos o un reporte de una instancia Odoo conectada -- "cuantas ordenes hay en cada estado", "ventas por cliente este ano", "que productos no rotan", "dame un listado de". Consulta en solo lectura agregando en el servidor y devuelve el resultado en el chat, o en HTML si el volumen lo pide. Menciona "reporte", "listado", "cuantos", "por cliente", "por mes", "ranking", "consulta", "read_group".
version: 0.1.0
---

# Reportes de solo lectura sobre una instancia Odoo

```bash
export ODOO_EX="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(find ~/.claude/plugins -type f -name odoo_ro.py -path '*odoo-explorer*' 2>/dev/null | head -1)")")}"
python3 "$ODOO_EX/scripts/odoo_connect.py" list     # que instancias hay
```

Si no hay ninguna instancia dada de alta, usa antes la skill `odoo-connect`.

**Solo lectura, siempre.** El cliente RPC bloquea por codigo cualquier metodo que no sea
de lectura. No busques rodeos.

## Agrega en el servidor, no en tu contexto

La diferencia entre un reporte que tarda un segundo y uno que se come la sesion:

```bash
# BIEN: PostgreSQL agrupa y devuelve 20 filas
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme read-group sale.order \
  --domain '[["state","in",["sale","done"]],["date_order",">=","2026-01-01"]]' \
  --fields '["amount_total:sum","id:count"]' --groupby '["partner_id"]'

# MAL: traerte 40.000 pedidos para sumarlos tu
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme search-read sale.order --limit 40000
```

Agrupar por periodo usa el sufijo de granularidad:

```bash
--groupby '["date_order:month"]'      # tambien :day, :week, :quarter, :year
--groupby '["partner_id","state"]'    # cruzado
```

Contar rapido:

```bash
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme count stock.picking \
  --domain '[["state","=","assigned"]]'
```

`search-read` es para las **muestras** (cinco registros para entender la forma del dato),
no para el reporte.

## Antes de consultar, mira los campos

```bash
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme fields sale.order
```

Comprueba que el campo existe, que es `store: true` (los no almacenados **no** se pueden
agrupar ni filtrar) y que el `selection` de un estado es el que crees. Los nombres de
estado cambian entre versiones y entre modulos a medida.

## Multiempresa

Si la instancia tiene varias companias, un reporte sin filtrar mezcla los datos de todas y
el numero sale mal. Comprueba y, si hay mas de una, pregunta cual quiere o filtra
explicitamente:

```bash
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme search-read res.company --fields name
--domain '[["company_id","=",1]]'
```

Ten en cuenta ademas que **lo que ves depende del usuario con el que te conectas**: sus
reglas de registro pueden ocultarte filas. Si un total no cuadra con lo que espera el
usuario, esa es la primera sospecha.

## Como entregarlo

- **Pocas filas**: tabla markdown en el chat. Es lo que quiere el 90% de las veces.
- **Muchas filas o varios cortes**: fichero en el proyecto del usuario, y le das la ruta.
- **Grafico o cuadro de mando**: HTML local. Si el usuario pide compartirlo, entonces un
  Artifact.

Di siempre de que fecha son los datos, que dominio aplicaste y cuantos registros hay
detras del agregado. Un reporte sin su filtro no es verificable.

## Lo que no es este skill

Si la pregunta es *como funciona* algo y no *cuanto hay*, es la skill `odoo-process`:
esa cruza el codigo fuente y produce un dossier con diagramas.
