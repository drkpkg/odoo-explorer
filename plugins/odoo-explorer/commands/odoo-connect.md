---
description: Conecta en solo lectura a una instancia Odoo, detecta su version y descarga el codigo fuente de esa serie
argument-hint: "[dominio o ip opcional]"
---

Usa la skill `odoo-connect` para dar de alta una instancia Odoo en **solo lectura**.

Datos de partida del usuario: $ARGUMENTS

Sigue el flujo completo: preguntar los datos de conexion en una sola tanda (dominio/ip,
http o https, puerto, base de datos, usuario, y un slug corto), sondear el servidor,
guardar la instancia, pasarle al usuario el comando `!` para que escriba **el** la
contrasena, verificar, descargar la fuente de la serie detectada y perfilar los modulos.

Nunca pidas la contrasena por el chat. Nunca ejecutes nada que escriba en la instancia.
