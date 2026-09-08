---
name: odoo-process
description: Debe usarse cuando el usuario pregunta como funciona un proceso de negocio en una instancia Odoo concreta -- "quiero saber el proceso de manufactura", "como funciona la venta aqui", "explicame el flujo de compras", "que pasa cuando confirmo una factura". Cruza el codigo fuente de la version con consultas de solo lectura a la instancia y produce un dossier HTML interactivo con diagramas Archify, siempre con la misma estructura. Menciona "proceso", "flujo", "como funciona", "paso a paso", "diagrama", "dossier".
version: 0.1.0
---

# Dossier de proceso Odoo

Produce **un dossier por proceso y por instancia**, con estructura fija. No inventes un
formato nuevo cada vez: rellenas un `dossier.json` con esquema cerrado y un script lo
compila. Si el proceso ya tiene dossier, **actualizalo en su sitio**; no crees otro.

## Antes de empezar

Hace falta una instancia dada de alta y verificada, y la fuente de su serie en cache. Si
no la hay, usa primero la skill `odoo-connect`. Comprueba:

```bash
export ODOO_EX="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(find ~/.claude/plugins -type f -name odoo_ro.py -path '*odoo-explorer*' 2>/dev/null | head -1)")")}"
python3 "$ODOO_EX/scripts/odoo_connect.py" list
python3 "$ODOO_EX/scripts/odoo_source.py" list
```

**Todo es de solo lectura.** Ver la regla completa en la skill `odoo-connect`.

## Metodo: las dos mitades

| La instancia responde | El codigo fuente responde |
|---|---|
| Que modulos hay y cuales son a medida | Que hace cada boton por dentro |
| Que campos y vistas se anadieron | La maquina de estados y quien la mueve |
| En que estados estan los registros hoy | Que registros se crean en cada paso |
| Que configuracion esta activada | Por que un estado avanza solo |

Ninguna mitad basta. Una afirmacion sin una de las dos como respaldo no entra en el
dossier: va a `open_questions`.

## Paso 1 — Identifica el proceso

Traduce la pregunta a un modelo raiz y unos modulos. Consulta
`references/procesos-odoo.md` para el mapa de los procesos habituales. Si la pregunta es
ambigua ("el proceso de ventas" puede ser el ciclo comercial o solo la entrega),
acota en una frase y sigue; no bloquees preguntando.

Verifica que el modelo existe **en esta instancia**:

```bash
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme model mrp.production
```

Si el modelo no existe, el modulo no esta instalado: dilo y ofrece el proceso equivalente
que si esta.

## Paso 2 — Recoge de la instancia

```bash
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme model mrp.production      # campos, vistas, campos manuales
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme states mrp.production     # estados reales y cuantos hay en cada uno
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme graph mrp.production --depth 1 --required-only
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme customizations --model mrp.production
```

La distribucion por estado es lo que convierte un manual generico en un diagnostico: si
el 60% de las ordenes abiertas estan en `confirmed`, el cuello de botella esta en la
reserva de material, no en la planta.

## Paso 3 — Lee el codigo fuente

```bash
python3 "$ODOO_EX/scripts/odoo_source.py" find-model mrp.production --serie 18.0
python3 "$ODOO_EX/scripts/odoo_source.py" grep "def action_confirm" --serie 18.0 --modules mrp
python3 "$ODOO_EX/scripts/odoo_source.py" module mrp --serie 18.0
```

Luego lee los ficheros con `Read`. Busca, en este orden:

1. El campo de estado y su `selection`: los estados posibles.
2. Los metodos `action_*` / `button_*`: que hace cada boton y a que estado lleva.
3. `_compute_state` o similar: los estados que **no** los pone un boton (muy importante,
   es lo que hace que un proceso "avance solo" y lo que mas confunde a los usuarios).
4. Que registros se crean: `.create(`, `_action_launch_stock_rule`, `_create_invoices`...
5. `_constrains` y las excepciones `UserError`: por que el proceso **se bloquea**.

Los modulos que salieron `fuera-de-la-fuente` en `odoo-connect` pueden cambiar todo esto.
Si uno de ellos toca el modelo raiz, dilo en `open_questions`: su codigo no esta en el
servidor y no puedes leerlo.

## Paso 4 — Crea el esqueleto

```bash
python3 "$ODOO_EX/scripts/build_dossier.py" scaffold --instance acme --process manufactura \
  --title "Proceso de manufactura" \
  --question "Como fabrica esta instancia, de la necesidad al producto en stock."
```

Crea `instances/acme/processes/manufactura/dossier.json` con **todas** las claves y los
cinco huecos de diagrama. Rellenalo con `Edit`/`Write`. El contrato de cada clave esta en
`references/contrato-dossier.md`. Reglas que no se negocian:

- `resumen` se escribe **el primero y para alguien que no es tecnico**: una frase que
  responda la pregunta, los puntos clave y que implica para el negocio. Sin nombres de
  modelo ni de metodo. Es lo unico que va a leer un responsable, y es lo que se ve en la
  vista Resumen del dossier.
- Cada paso de `steps` lleva `evidence`: fichero del fuente, o comando RPC ejecutado.
- Los `count` salen de la instancia, nunca se estiman.
- `this_instance` es la seccion que justifica el trabajo: que tiene **esta** implantacion
  que no tiene el Odoo de manual.
- Lo que no sepas va a `open_questions`. No rellenes huecos con lo que "suele pasar".

## Paso 5 — Los cinco diagramas

Se generan con **Archify** (skill `archify`, ya instalada). Un JSON por hueco, en
`diagrams/`, validado y compilado:

| Hueco | Tipo Archify | Que muestra |
|---|---|---|
| `map` | `architecture` | Los modelos que participan y como se enlazan |
| `lifecycle` | `lifecycle` | Estados del documento principal, con los conteos reales |
| `flow` | `workflow` | El proceso completo por carriles, con ramas y excepciones |
| `triggers` | `sequence` | La cadena de llamadas real al pulsar cada boton |
| `data` | `dataflow` | Que registros se crean y que llega a stock o a contabilidad |

Para cada uno:

```bash
cd ~/.claude/skills/archify
node bin/archify.mjs validate lifecycle <ruta>/diagrams/02-lifecycle.lifecycle.json --quality showcase --json
node bin/archify.mjs deliver  lifecycle <ruta>/diagrams/02-lifecycle.lifecycle.json <ruta>/diagrams/02-lifecycle.lifecycle.html --quality showcase --json
```

Las trampas de geometria que ya costaron rondas de correccion estan en
`references/archify-odoo.md`. **Leelo antes del primer diagrama**: ahorra reintentos.

Si el usuario solo quiere una respuesta rapida, genera `lifecycle` y `flow` y deja los
otros tres huecos vacios: el dossier los muestra como pendientes, la estructura no cambia.

## Paso 6 — Compila y entrega

```bash
python3 "$ODOO_EX/scripts/build_dossier.py" validate instances/acme/processes/manufactura/dossier.json
python3 "$ODOO_EX/scripts/build_dossier.py" render   instances/acme/processes/manufactura/dossier.json
python3 "$ODOO_EX/scripts/build_dossier.py" index --instance acme
```

Da al usuario la ruta `file://` del dossier y la del indice de la instancia.

El dossier trae un interruptor **Resumen / Completa**. En Resumen se ocultan la traza
tecnica, los campos y la evidencia: es la vista para mandarsela a un responsable. En
Completa se ve todo. La eleccion se recuerda en el navegador de quien lo abre. Mencionalo
cuando entregues: es lo que permite compartir el mismo fichero con perfiles distintos.

## Artifact: solo si lo pide

El entregable por defecto es HTML local. Si el usuario pide compartirlo, **entonces**
publica un Artifact con el mismo contenido. Los diagramas Archify son HTML autocontenido:
en un Artifact van embebidos en la pagina, no como `iframe` a fichero local.

## Al terminar

Responde la pregunta que hizo el usuario en 3-6 frases, con lo que de verdad importa de
**su** instancia, y despues enlaza el dossier. El dossier es el respaldo; la respuesta va
en el chat.
