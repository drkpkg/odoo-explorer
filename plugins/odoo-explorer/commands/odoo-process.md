---
description: Documenta un proceso de negocio de la instancia conectada como dossier HTML con diagramas
argument-hint: "<proceso> [instancia]"
---

Usa la skill `odoo-process` para producir el dossier del proceso que pide el usuario.

Proceso solicitado: $ARGUMENTS

Cruza el codigo fuente cacheado de la serie de la instancia con consultas de solo lectura,
rellena el `dossier.json` de esquema fijo, genera los diagramas con Archify, compila el
HTML y dale al usuario la ruta.

Si hay varias instancias dadas de alta y el usuario no dijo cual, preguntaselo antes de
empezar. Si no hay ninguna, usa primero la skill `odoo-connect`.

Responde primero en el chat, en pocas frases, lo que de verdad importa de **su**
instancia; el dossier va detras como respaldo.
