---
description: Consulta datos agregados de la instancia Odoo conectada, en solo lectura
argument-hint: "<que quieres saber>"
---

Usa la skill `odoo-report` para responder con datos de la instancia.

Pregunta: $ARGUMENTS

Agrega en el servidor con `read-group`; no te traigas miles de registros. Comprueba antes
que los campos existen y son almacenados. Si la instancia es multiempresa, aclara o filtra
la compania. Di siempre el dominio aplicado y cuantos registros hay detras del agregado.
