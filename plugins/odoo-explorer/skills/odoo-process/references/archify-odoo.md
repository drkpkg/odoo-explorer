# Archify aplicado a procesos Odoo

Archify valida la geometria antes de entregar. Estas son las trampas que ya costaron
rondas de correccion al construir el primer dossier: aplicarlas de entrada ahorra
reintentos.

Flujo por diagrama: escribe el JSON -> `validate` -> corrige **solo** el `subject`
diagnosticado -> `validate` otra vez -> `deliver`. Nunca edites un JSON despues de que
pase la validacion final.

```bash
cd ~/.claude/skills/archify
node bin/archify.mjs validate <tipo> <ruta>.json --quality showcase --json
node bin/archify.mjs deliver  <tipo> <ruta>.json <ruta>.html --quality showcase --json
```

## Nombres de fichero (los fija el scaffold)

```
diagrams/01-map.architecture.json       -> .html
diagrams/02-lifecycle.lifecycle.json    -> .html
diagrams/03-flow.workflow.json          -> .html
diagrams/04-triggers.sequence.json      -> .html
diagrams/05-data.dataflow.json          -> .html
```

## `lifecycle` — el ciclo de vida del documento

El mas util y el mas quisquilloso.

- El carril principal usa `col` 0..4. Los carriles de eventos/terminales usan `col` 0..2,
  y **la columna N de un carril de eventos se alinea bajo la columna N+2 del principal**.
  Es decir: solo puedes colgar algo debajo de las columnas 2, 3 y 4. Diseña el raiz
  sabiendolo, o acabaras con flechas que atraviesan estados.
- Las transiciones entre columnas contiguas del raiz necesitan `"route": "straight"`, o
  saltara `composition/micro-segment` (un tramo de 7 px).
- Sus etiquetas se solapan con los estados vecinos: ponles `"labelDy": -28` para
  subirlas por encima del raiz.
- Una transicion vertical hacia un terminal quiere `"labelDy": 34` para que la etiqueta no
  caiga encima del estado de origen.
- `meta.viewBox[1]` tiene un minimo calculado segun los carriles. El validador te dice el
  numero exacto: usalo, no lo adivines.
- Prefiere **dos carriles** (principal + terminales). Con tres el alto se dispara y las
  rutas se cruzan.

Traduccion desde Odoo:

- `type: "start"` el estado inicial (`draft`), `"active"` los de trabajo, `"decision"` el
  de control previo al cierre (`to_close`), `"success"` el final bueno (`done`),
  `"failure"` los terminales (`cancel`), `"waiting"` las esperas reales.
- La etiqueta va en negocio ("Confirmada") y el `sublabel` lleva la clave tecnica
  (`confirmed`). El administrador necesita las dos.
- La etiqueta de la transicion es el metodo: `action_confirm()`. Cuando el estado cambia
  **solo**, dilo asi: "primer consumo registrado", no un nombre de boton inventado.
- Las `cards` son para lo que no cabe en el diagrama: donde se atasca el proceso, que
  transicion no la dispara ningun boton.

## `architecture` — el mapa de modelos

- Un nodo por modelo, no por tabla. Tipos: `database` para los modelos que almacenan el
  documento, `backend` para los de proceso, `external` para lo que sale del sistema.
- Como maximo 12 nodos. `odoo_probe.py graph --required-only` ya poda lo accesorio; si
  aun sobran, quita los modelos que no aparezcan en ningun paso de `steps`.
- La etiqueta de la relacion es el campo real: `move_raw_ids`, `bom_id`.

## `workflow` — el proceso extremo a extremo

- Usa `schema_version: 2` en los nuevos.
- Un carril por rol de `actors`. Que el camino feliz quede recto y horizontal.
- Las ramas (falta stock, aprobacion, rechazo) salen del nodo del camino feliz mas
  cercano, no de un nodo suelto.

## `sequence` — que ejecuta cada boton

- Los participantes son modelos, no personas: `mrp.production`, `stock.move`,
  `stock.quant`.
- Cada mensaje es una llamada real leida en la fuente. Si no la leiste, no la dibujes.
- Si las etiquetas de participante no caben, `meta.column_fit: "spread"` antes de acortar
  nombres: `stock.move.line` no se abrevia.

## `dataflow` — el movimiento de datos

- Origen: el documento. Transformaciones: los metodos. Destinos: `stock.quant`,
  `account.move`, `stock.valuation.layer`.
- Es el diagrama que responde "y esto que efecto tiene en mi stock y en mi contabilidad",
  que suele ser la pregunta de verdad detras de la pregunta.

## Idioma

Escribe el contenido en el idioma del usuario. `meta.locale` solo acepta `en` y `zh-CN`:
para un dossier en espanol, **omitelo** y avisa una vez de que los controles del visor
(Legend, Export, atajos) quedan en ingles. Los identificadores de Odoo (`mrp.production`,
`action_confirm`) no se traducen nunca.

## Presentacion

Omite `meta.visual_preset` salvo que el usuario pida un estilo concreto. Omite
`meta.animation` salvo que el dossier sea para presentar. Sin `meta.subtitle`.
