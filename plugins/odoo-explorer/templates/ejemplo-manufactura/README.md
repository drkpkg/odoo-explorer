# Ejemplo trabajado: proceso de manufactura

Datos **ficticios**, estructura real. Sirve para ver la forma que debe tener un
`dossier.json` completo y un diagrama `lifecycle` que pasa la validacion showcase de
Archify a la primera (fijate en `route: "straight"` y en los `labelDy`).

No lo copies como si fueran hechos: los estados, los conteos y las desviaciones se sacan
siempre de la instancia del usuario.

Para verlo compilado:

```bash
cp -r . /tmp/ejemplo && cd /tmp/ejemplo
cd ~/.claude/skills/archify && node bin/archify.mjs deliver lifecycle \
  /tmp/ejemplo/diagrams/02-lifecycle.lifecycle.json \
  /tmp/ejemplo/diagrams/02-lifecycle.lifecycle.html --quality showcase
```
