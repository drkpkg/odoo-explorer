---
name: odoo-setup
description: Debe usarse cuando alguien empieza a usar odoo-explorer por primera vez, pregunta que necesita instalar, o algo no funciona -- "no me salen los diagramas", "por donde empiezo", "que hace falta para usar esto", "me da error". Diagnostica el entorno (Python, Node, Archify, disco, fuentes descargadas) y explica en lenguaje llano que falta y como arreglarlo. Menciona "instalar", "configurar", "empezar", "primeros pasos", "no funciona", "requisitos", "diagnostico".
version: 0.1.0
---

# Puesta en marcha y diagnostico

Esta skill es para personas que **no son desarrolladores**. Habla en llano: nada de
"dependencias", "entorno virtual" ni "runtime". Di que falta, por que importa y que hacer.

## Diagnostico

```bash
export ODOO_EX="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$(find ~/.claude/plugins -type f -name odoo_ro.py -path '*odoo-explorer*' 2>/dev/null | head -1)")")}"
python3 "$ODOO_EX/scripts/doctor.py" --json
```

Devuelve `listo` (si se puede trabajar), `diagramas_disponibles`, y por cada pieza si esta
bien y como arreglarla.

## Que hacer con cada resultado

**Todo en verde** — dilo en una frase y pasa directamente a conectar la instancia. No le
recites la lista de comprobaciones a quien no la ha pedido.

**Falta Node o Archify** — el trabajo se puede hacer igual: el dossier se genera y los
diagramas quedan marcados como pendientes. Explicalo asi, sin dramatizar. Ofrece
instalarlo:

```bash
python3 "$ODOO_EX/scripts/doctor.py" --instalar
```

Descarga Archify de internet. **Pide permiso antes de ejecutarlo.** Si no hay Node, hay
que instalarlo desde nodejs.org primero, y eso lo hace la persona, no tu.

**Falta Python 3.8+** — es lo unico imprescindible. Sin el no hay nada que hacer;
indicale python.org y para.

**Falta espacio en disco** — cada version de Odoo ocupa unos 1,2 GB descomprimida. O
libera espacio, o cambia la carpeta con `ODOO_SRC_CACHE`.

## Primera vez: el orden

1. Diagnostico (arriba). Arregla lo imprescindible.
2. Conectar la primera instancia. Para alguien sin perfil tecnico, **usa el asistente**:
   dile que escriba esta linea en el prompt de Claude Code (el `!` de delante incluido) y
   que conteste las preguntas.

   ```
   ! python3 "$ODOO_EX/scripts/odoo_connect.py" wizard
   ```

   Pregunta servidor, puerto, base, usuario y contrasena (oculta al teclear), verifica el
   acceso, detecta la version y se ofrece a descargar el codigo fuente. Es **un solo
   comando** y lo demas son respuestas.

3. Ya esta. A partir de ahi todo es conversacion: "documenta el proceso de compras",
   "cuantas facturas hay sin pagar".

## Errores frecuentes, en llano

| Lo que ve la persona | Que pasa de verdad | Que decirle |
|---|---|---|
| `Connection refused` | El servidor no responde en ese puerto | Revisa el dominio y el puerto; puede hacer falta VPN |
| `Autenticacion fallida` | Usuario, contrasena o base incorrectos | Prueba a entrar por el navegador con esos mismos datos |
| `databases: null` | El servidor oculta la lista de bases | Es lo normal en produccion: hay que preguntar el nombre exacto |
| Faltan diagramas en el dossier | No hay Node o Archify | El contenido esta completo; los diagramas se pueden anadir despues |
| Un modulo no aparece en la fuente | Es a medida, de OCA o Enterprise | Se documenta desde la instancia, y se dice que no hubo codigo que leer |

## Lo que nunca hay que hacer

No instales nada sin pedir permiso. No pidas la contrasena por el chat. No ejecutes nada
que escriba en la instancia del cliente: todo es de solo lectura.
