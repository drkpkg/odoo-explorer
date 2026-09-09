---
description: Conecta en solo lectura a una instancia Odoo, detecta su version y descarga el codigo fuente de esa serie
argument-hint: "[url, dominio o ip de tu Odoo]"
---

Usa la skill `odoo-connect` para dar de alta una instancia Odoo en **solo lectura**.

Datos de partida del usuario: $ARGUMENTS

Camino corto, que es el habitual: pide la direccion (dominio, ip o la url del navegador),
sondeala con `odoo_connect.py probe --url` -- eso detecta protocolo, puerto, version,
edicion y, si el servidor las publica, las bases de datos --, ofrece las bases con
`AskUserQuestion`, y pide usuario y contrasena. Ejecuta tu `odoo_connect.py setup` con la
contrasena **por STDIN** (nunca como argumento): guarda, verifica y descarga la fuente.
Luego perfila los modulos.

Avisa una vez de donde quedan las credenciales y de no compartir `instances/` ni el
transcript. No leas ni imprimas nunca el contenido de `.env`. Nunca ejecutes nada que
escriba en la instancia.
