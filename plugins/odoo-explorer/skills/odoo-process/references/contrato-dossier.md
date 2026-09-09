# Contrato de `dossier.json`

Esquema cerrado: `odoo-explorer/dossier@1`. `build_dossier.py scaffold` lo crea con todas
las claves; tu solo las rellenas. **No anadas claves nuevas ni cambies el orden de las
secciones**: la estructura fija es lo que permite comparar dos procesos o dos clientes.

Una seccion sin datos se renderiza vacia y dice que falta. Eso es correcto y preferible a
rellenarla con relleno generico.

## El formato importa tanto como el contenido

El render no adivina: cada campo tiene una forma. **Un texto suelto donde va una lista de
frases se renderizaba letra a letra** —una frase de 200 caracteres salia como 200
vinetas—, y una fila con claves que no existen sale como columnas en blanco. Por eso
`build_dossier.py render` **se niega a compilar** un dossier con el formato mal, y
`validate` te dice la ruta exacta del campo.

**Listas de frases** (`["...", "..."]`, nunca una frase suelta):
`resumen.puntos`, `resumen.implicaciones`, `scope.covers`, `scope.excludes`,
`scope.modules`, `steps[].what_happens`, `steps[].creates`, `this_instance.findings`,
`this_instance.deviations`, `evidence.source_refs`, `evidence.rpc_calls`,
`open_questions`.

**Listas de filas**, con estas claves exactas y nada mas (lo que no este en la lista no se
ve en el HTML):

| Campo | Claves de cada fila |
|---|---|
| `actors` | `role`, `does`, `group` |
| `models` | `model`, `role`, `module`, `count`, `custom` |
| `lifecycle.states` | `key`, `label`, `count`, `means` |
| `triggers` | `ui`, `method`, `effect`, `source` |
| `key_fields` | `model`, `field`, `label`, `type`, `why`, `custom` |
| `config` | `where`, `option`, `value`, `effect` |
| `this_instance.volumes` | `label`, `value` |
| `steps[].evidence` | `kind`, `ref` |

Ojo con `triggers`: es `ui` (no `button`) y `source` (no `file`). Y `steps[].evidence` es
una **lista** de objetos, aunque solo haya uno: `[{"kind": "source", "ref": "..."}]`.

El resto de campos son texto plano. Nada de markdown dentro de los valores: el render
escapa el HTML, asi que `**negrita**` sale literal.

## Clave por clave

`process` — `slug`, `title`, `question`. La `question` es la pregunta del usuario
reformulada en una frase; encabeza el dossier.

`instance` — se rellena solo desde `instance.json`. No lo toques.

`resumen` — **la seccion que mas se lee y la unica que veran los no tecnicos.**
`en_una_frase` responde la pregunta del usuario sin un solo nombre de modelo ni de metodo.
`puntos` son 3-5 hechos concretos con cifras de la instancia. `implicaciones` es lo que
deberia hacer alguien con esa informacion. Si esto suena a manual generico, esta mal
escrito: tiene que hablar de **esta** empresa.

`scope` — `modules` (los que de verdad participan), `covers` (3-5 frases de que abarca) y
`excludes` (lo que dejas fuera **y por que**: modulo no instalado, o pertenece a otro
dossier). Un alcance honesto vale mas que uno amplio.

`actors` — `role`, `does`, `group`. El grupo de acceso real de Odoo, no una etiqueta
inventada.

`models` — `model`, `role` (que papel juega en **este** proceso, no su descripcion
generica), `module`, `count` (de la instancia), `custom` (booleano).

`lifecycle` — `model`, `field`, y `states` con `key`, `label`, `count` y `means`. Los
`count` salen de `odoo_probe.py states`. `means` explica que implica estar ahi, no repite
la etiqueta.

`steps` — el corazon del dossier. Por paso:

| Campo | Que va |
|---|---|
| `title` | Que pasa, en lenguaje de negocio |
| `actor` | Quien lo hace |
| `ui` | Donde se hace: menu y boton reales |
| `model` | Modelo que se toca |
| `trigger` | Que lo dispara, con el metodo: `Boton Confirmar -> action_confirm()` |
| `state_from` / `state_to` | Transicion, o `(no existe)` si el paso crea el registro |
| `what_happens` | Que ocurre **por dentro**. Aqui es donde el codigo fuente paga |
| `creates` | Que registros aparecen o cambian |
| `evidence` | `{"kind":"source","ref":"addons/mrp/models/mrp_production.py :: action_confirm"}` o `{"kind":"rpc","ref":"<comando>"}` |

Un paso sin `evidence` no se publica.

`triggers` — tabla resumen boton -> metodo -> efecto -> fichero. Es el indice tecnico del
proceso; alimenta el diagrama `sequence`.

`key_fields` — solo los campos que **gobiernan el comportamiento**. Un `why` que diga por
que importa. Si es de Studio o de un modulo a medida, `custom: true`.

`config` — `where` (ruta del ajuste), `option`, `value` (el valor **en esta instancia**),
`effect`. Es lo que explica por que aqui el proceso no es el del manual.

`this_instance` — `volumes` (tarjetas de cifras reales), `findings` (lo que se deduce de
los datos: cuellos de botella, estados atascados) y `deviations` (campos manuales,
modulos fuera de la fuente, automatizaciones). Si esta seccion queda pobre, el dossier no
aporta mas que la documentacion oficial.

`diagrams` — no lo edites salvo para cambiar `caption`. Los cinco huecos y sus rutas los
fija el scaffold.

`evidence` — `source_refs` (ficheros leidos) y `rpc_calls` (comandos ejecutados). Permite
que otra persona repita el analisis.

`open_questions` — lo que no pudiste comprobar. Codigo a medida que no esta en el
servidor, comportamiento que dependeria de ejecutar algo (y no se ejecuta: solo lectura).
Es una seccion de calidad, no un fracaso.

## Antes de entregar

```bash
python3 "$ODOO_EX/scripts/build_dossier.py" validate <ruta>/dossier.json
```

`problems` hay que arreglarlos: `render` no compila hasta que esten a cero. `avisos` son
cosas que escribiste y no se van a ver (una clave que ninguna columna lee, un paso sin
evidencia): repasalos, casi siempre son un error de tecleo.

Al compilar, `render` devuelve ademas sus propios `avisos` mirando el HTML ya generado
(vinetas de un solo caracter, filas vacias, demasiadas secciones sin datos). Si sale
alguno, el dossier no esta listo para entregar.

## Al actualizar un dossier existente

Edita el `dossier.json` que ya hay y vuelve a renderizar. Conserva `open_questions` que
sigan abiertas. No crees `manufactura-v2`.
