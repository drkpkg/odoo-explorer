---
name: odoo-connect
description: Debe usarse cuando el usuario quiere conectarse a una instancia Odoo en linea para consultarla, auditarla o documentarla sin modificarla. Cubre el alta guiada de la instancia (ip/dominio, puerto, usuario, contrasena, base de datos), la deteccion de version y edicion, y la descarga y cacheo del codigo fuente de esa serie. Menciona "conectar", "instancia", "servidor Odoo", "XML-RPC", "solo lectura", "que version", "descargar fuente", "base de datos".
version: 0.1.0
---

# Conectar a una instancia Odoo (solo lectura)

## Regla numero uno: SOLO LECTURA

Estas instancias son **produccion de un cliente**. Nunca ejecutes `create`, `write`,
`unlink`, `copy`, `button_*`, `action_*`, ni instales o actualices modulos, ni toques
parametros, ni escribas por SQL o por la UI.

`scripts/odoo_ro.py` aplica la regla por codigo: toda llamada pasa por
`assert_read_only()` contra una lista blanca. **No amplies `ALLOWED_METHODS`.** Si algo
necesita una escritura para avanzar, proponla al usuario y que la ejecute el mismo fuera
de esta herramienta.

## Localiza los scripts una vez

```bash
export ODOO_EX="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(find ~/.claude/plugins -type f -name odoo_ro.py -path '*odoo-explorer*' 2>/dev/null | head -1)")")}"
ls "$ODOO_EX/scripts"
```

Todos los comandos se ejecutan **desde el directorio de trabajo del usuario**: ahi se crea
`instances/`. No lo cambies de sitio sin que lo pida.

## Elige el camino segun con quien hablas

**Si la persona no tiene perfil tecnico** (o no sabes si lo tiene): el asistente. Un solo
comando, que escribe **ella** en el prompt de Claude Code con el `!` de delante:

```
! python3 "$ODOO_EX/scripts/odoo_connect.py" wizard
```

Pregunta servidor, protocolo, puerto, base, usuario y contrasena (oculta al teclear),
verifica el acceso, detecta version y edicion, y se ofrece a descargar el codigo fuente.
Si el servidor publica la lista de bases, la muestra numerada para elegir.

Tu no puedes ejecutarlo: necesita una terminal interactiva. Presentalo asi, sin jerga:
"copia esta linea y contesta las preguntas; la contrasena no se ve al escribirla y no
llega al chat". Cuando termine, confirma con `odoo_connect.py list`.

**Si la persona es tecnica** o quiere automatizarlo, sigue el flujo por pasos de abajo.

## El flujo paso a paso

### 1. Pregunta los datos de conexion

Preguntalo en el chat, en una sola tanda, y **nunca pidas la contrasena por el chat**.
Si tienes que hacer varias preguntas cerradas (http o https, que base de las que expone el
servidor), usa `AskUserQuestion`: para alguien no tecnico es mucho mas facil elegir de una
lista que escribir un valor exacto.

- dominio o IP, y si es `http` o `https`
- puerto (8069 tipico en http; en https suele ir sin puerto)
- base de datos (si no la sabe, el paso 2 la averigua)
- usuario
- un `slug` corto para nombrar la carpeta: `cliente-prod`, `acme`, ...

### 2. Sondea el servidor antes de nada

```bash
python3 "$ODOO_EX/scripts/odoo_connect.py" probe --host erp.cliente.com --protocol https
```

Devuelve version, serie, edicion y la lista de bases **si el servidor la expone**. Si
`databases` es `null`, el listado esta deshabilitado (`list_db=False`) y hay que
preguntarle el nombre exacto de la base al usuario.

### 3. Guarda la instancia

```bash
python3 "$ODOO_EX/scripts/odoo_connect.py" save --instance acme \
  --host erp.cliente.com --protocol https --db acme_prod --user consultor \
  --label "ACME S.A. (produccion)"
```

Crea `instances/acme/instance.json` y un `.gitignore` que protege las credenciales.

### 4. La contrasena la escribe el USUARIO, no tu

Dale este comando para que **lo ejecute el** con el prefijo `!` (asi no aparece ni en el
chat ni en el historial):

```
! read -rsp 'Password Odoo: ' P && printf '%s' "$P" | python3 "$ODOO_EX/scripts/odoo_connect.py" set-password --instance acme; unset P
```

Queda en `instances/acme/.env` con permisos `600`. Alternativa valida: que exporte
`ODOO_PASSWORD` en su shell antes de abrir la sesion.

Si el usuario decide pegarte la contrasena en el chat de todos modos, es su decision:
usala, pero avisale una vez de que queda en el transcript.

### 5. Verifica y detecta la version

```bash
python3 "$ODOO_EX/scripts/odoo_connect.py" verify --instance acme
```

Autentica, detecta **serie** (`18.0`) y **edicion** (`community` / `enterprise`), y lo
guarda en `instance.json`.

### 6. Descarga el codigo fuente de esa serie

```bash
python3 "$ODOO_EX/scripts/odoo_source.py" ensure 18.0
```

Descarga `https://nightly.odoo.com/18.0/nightly/src/odoo_18.0.latest.zip` (~370 MB), lo
descomprime en `~/.cache/odoo-src/18.0/` y escribe `SOURCE.json`. Solo la primera vez por
serie: las siguientes es instantaneo. Avisa al usuario de que va a descargar antes de
lanzarlo.

**Por que hace falta la fuente.** La instancia dice *que* hay configurado y *que* paso.
El codigo fuente dice *como funciona el proceso*: la maquina de estados, que hace
`action_confirm`, que registros crea cada boton. Eso no esta en `ir.model.fields` ni en
ninguna tabla. Un dossier sin fuente es adivinanza.

**Si la instancia es Enterprise:** el nightly publico solo trae Community. Los modulos
enterprise se documentan desde los metadatos de la instancia (campos, vistas, acciones) y
se marca explicitamente que no hubo codigo que leer. Dilo en el dossier, no lo disimules.

**Si es Odoo Online (`saas~18.1`):** no hay fuente publica de esa serie. Se usa la base
(`18.0`) y se avisa de que puede haber diferencias.

### 7. Perfila la instancia

```bash
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme overview --save
python3 "$ODOO_EX/scripts/odoo_probe.py" -i acme modules --serie 18.0
```

`modules` clasifica lo instalado contra la fuente oficial. Lo que sale como
`fuera-de-la-fuente` es a medida, OCA o Enterprise: **son los modulos que mas cambian el
comportamiento y los que hay que mirar primero**. No clasifiques por el campo `author`:
es texto libre y se falsea con frecuencia.

## Consultas sueltas y reportes

```bash
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme whoami
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme count sale.order --domain '[["state","=","sale"]]'
python3 "$ODOO_EX/scripts/odoo_ro.py" -i acme read-group account.move \
    --domain '[["move_type","=","out_invoice"]]' --fields '["amount_total:sum"]' \
    --groupby '["partner_id"]'
```

Para reportes con volumen usa `read-group`, no `search-read` con limite alto: agrega en
el servidor en vez de traerte miles de registros.

## Al terminar

Resume: version y edicion, base, cuantos modulos instalados y cuantos fuera de la fuente,
y donde quedo la fuente cacheada. Si el usuario venia a entender un proceso, pasa a la
skill `odoo-process`.
