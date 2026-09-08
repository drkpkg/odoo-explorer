# odoo-explorer

Marketplace de un solo plugin para Claude Code: **explorar instancias Odoo en linea, en
solo lectura**, y entender sus procesos.

Pensado para el administrador o consultor que se conecta a la instancia de un cliente y
necesita responder *"como funciona aqui el proceso de manufactura"* sin tocar nada.

## Que hace

1. **Conecta** a una instancia por XML-RPC preguntando dominio/ip, puerto, base, usuario y
   contrasena (que nunca pasa por el chat).
2. **Detecta** la version y la edicion del servidor.
3. **Descarga** el codigo fuente de esa serie desde nightly.odoo.com si no esta en cache,
   lo descomprime en `~/.cache/odoo-src/<serie>/` y lo reutiliza para siempre.
4. **Cruza** las dos mitades: la instancia dice que hay configurado y en que estado esta
   todo; el codigo fuente dice como funciona el proceso por dentro.
5. **Entrega** un dossier HTML interactivo, con la misma estructura siempre y cinco
   diagramas generados con [Archify](https://github.com/tt-a1i/archify).

## Solo lectura, por codigo

`scripts/odoo_ro.py` filtra toda llamada contra una lista blanca de metodos de lectura.
`create`, `write`, `unlink`, `button_*` y compania fallan **antes de salir a la red**. La
lista blanca no se amplia.

## Instalar

```
/plugin marketplace add drkpkg/odoo-explorer
/plugin install odoo-explorer@odoo-explorer
```

¿No eres desarrollador? Empieza por **[docs/empezar.md](../../docs/empezar.md)**: cuatro pasos y
ningún comando que entender.

Requiere:

- Python 3.8+ (solo libreria estandar)
- Node 18+ y el skill [`archify`](https://github.com/tt-a1i/archify) instalado:
  `npx skills add tt-a1i/archify -g`
- ~400 MB de disco por serie de Odoo cacheada

## Usar

```
/odoo-setup                                  comprueba que todo esta listo
/odoo-connect erp.cliente.com                dar de alta una instancia
/odoo-process manufactura                    dossier de un proceso
/odoo-report ventas por cliente este ano     datos agregados
/odoo-instances                              que hay dado de alta
```

Para quien no maneja terminal, `/odoo-connect` ofrece un asistente de un solo comando que
pregunta todo paso a paso y oculta la contrasena al teclearla.

Los datos viven en el proyecto donde trabajes:

```
instances/<slug>/
├── instance.json          servidor, base, usuario, serie, edicion
├── .env                   contrasena, chmod 600, gitignoreada
├── profile.json           companias, modulos, idiomas
├── index.html             indice de procesos de esta instancia
└── processes/<proceso>/
    ├── dossier.json       contenido con esquema fijo
    ├── index.html         el dossier compilado
    └── diagrams/          los cinco diagramas Archify
```

## La estructura fija

Un dossier tiene siempre estas once secciones, en este orden. Una seccion sin datos se
muestra vacia y dice que falta; nunca desaparece.

1. Alcance · 2. Quien interviene · 3. Mapa de modelos · 4. Ciclo de vida del documento ·
5. El proceso paso a paso · 6. Que ejecuta cada accion · 7. Movimiento de datos ·
8. Campos clave · 9. Configuracion que cambia el comportamiento · 10. Esta instancia en
concreto · 11. Evidencia

Encabezandolas hay un **resumen** en lenguaje de negocio, y un interruptor
**Resumen / Completa** que oculta o muestra el detalle tecnico. El mismo fichero le sirve
a un consultor y a un gerente.

Lo que hace util al dossier es la seccion 10: lo que separa a **esta** implantacion del
Odoo de manual.

`build_dossier.py export` genera ademas **un solo HTML** con los diagramas dentro, para
enviarlo por correo: se abre con doble clic, sin internet y sin instalar nada.

## No es

- No es una herramienta de desarrollo de modulos: para eso esta
  [`odoo-curated`](https://github.com/drkpkg/odoo-curated).
- No escribe en la instancia, ni instala modulos, ni ejecuta acciones.
- No sustituye a la documentacion oficial de Odoo: la aterriza en una instancia concreta.

MIT.
