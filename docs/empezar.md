# Empezar, sin ser técnico

Esta guía es para quien sabe de Odoo pero no de programación. No hace falta entender nada
de lo que pasa por dentro: son cuatro pasos, y luego todo es conversación.

## Qué es esto, en una frase

Te conectas a un Odoo, y Claude te explica cómo funciona cualquier proceso de esa
instancia concreta —con diagramas— sin tocar ni un dato.

**Nunca escribe nada.** Está impedido por código, no por buena voluntad: cualquier
intento de modificar algo falla antes siquiera de salir a internet.

## Lo que necesitas

- **Claude Code** instalado ([claude.com/claude-code](https://claude.com/claude-code)).
- **Los datos de acceso** a la instancia: dirección, base de datos, usuario y contraseña.
  Con un usuario de solo lectura sobra.
- **Node.js** ([nodejs.org](https://nodejs.org)) si quieres diagramas. Sin él todo lo
  demás funciona igual; solo faltan las imágenes.

Si no sabes si lo tienes, no lo compruebes tú: pregúntale a Claude *"¿está todo listo para
usar odoo-explorer?"* y él lo mira.

## Paso 1 — Instalar

En Claude Code, escribe estas dos líneas:

```
/plugin marketplace add drkpkg/odoo-explorer
/plugin install odoo-explorer@odoo-explorer
```

## Paso 2 — Comprobar

```
/odoo-setup
```

Te dice si falta algo y qué hacer. Si falta Node, te lo dirá y te ofrecerá seguir sin
diagramas.

## Paso 3 — Conectar tu Odoo

```
/odoo-connect
```

Claude te va a ofrecer un asistente: una línea que copias, y luego solo respondes
preguntas —dirección, base de datos, usuario, contraseña—. **La contraseña no se ve
mientras la escribes y no aparece en la conversación**: se guarda en tu ordenador en un
fichero que solo tú puedes leer.

Al terminar te preguntará si descarga el código de tu versión de Odoo. Di que sí. Son unos
370 MB y tarda un minuto, pero solo la primera vez: es lo que permite explicar *cómo*
funcionan las cosas y no solo *qué* hay.

## Paso 4 — Preguntar

Ya está. A partir de aquí escribes en tu idioma:

```
/odoo-process manufactura
```

> Quiero entender el proceso de compras de principio a fin

> ¿Cuántas facturas hay sin pagar y de qué clientes?

> ¿Por qué no me deja validar una entrega?

## Lo que recibes

Un documento que se abre en el navegador con dos vistas:

- **Resumen** — qué pasa, en lenguaje de negocio, con las cifras de tu empresa. Es la que
  puedes enviarle a un gerente.
- **Completa** — además, el detalle técnico: qué hace cada botón por dentro, qué campos
  mandan, de dónde sale cada afirmación.

El interruptor está arriba del todo. Es el mismo documento: cada quien lo lee al nivel que
necesita.

Siempre tiene la misma estructura, para cualquier proceso y cualquier cliente. Eso permite
comparar y saber dónde mirar sin releerlo entero.

## Enviárselo a alguien

Pídele a Claude *"exporta el dossier para enviarlo"*. Genera **un solo fichero** con los
diagramas dentro. Se abre con doble clic, sin internet y sin instalar nada.

## Si algo falla

Díselo a Claude tal cual, con el mensaje que te salga. Los fallos habituales:

| Lo que ves | Qué pasa |
|---|---|
| `Connection refused` | La dirección o el puerto no son esos, o hace falta VPN |
| `Autenticación fallida` | Usuario, contraseña o base incorrectos. Pruébalos en el navegador |
| No aparecen los diagramas | Falta Node.js. El contenido está completo igualmente |

## Lo que esta herramienta no hace

- No modifica nada en tu Odoo. Ni un dato, ni un módulo, ni un ajuste.
- No sustituye a la documentación oficial de Odoo: la aterriza en **tu** instancia, con
  tus módulos, tu configuración y tus cifras.
- No ve el código de los módulos hechos a medida por terceros si no están publicados: en
  ese caso te lo dice claramente en vez de inventárselo.
