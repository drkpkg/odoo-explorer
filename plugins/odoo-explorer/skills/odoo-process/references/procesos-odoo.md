# Mapa de procesos Odoo: por donde entrar

Punto de entrada para traducir una pregunta de negocio a un modelo raiz. **Nada de aqui
es un hecho sobre la instancia del usuario**: los estados, los metodos y los modulos se
confirman siempre contra la fuente de esa serie y contra la propia instancia. Odoo cambia
estos detalles entre versiones (los estados de `account.payment`, por ejemplo, cambiaron
entre 17 y 18).

## Los procesos habituales

| Pregunta del usuario | Modelo raiz | Modulos | Campo de estado | Metodos que mover el proceso |
|---|---|---|---|---|
| Proceso de venta | `sale.order` | `sale`, `sale_stock` | `state` | `action_confirm`, `_create_invoices` |
| Proceso de compra | `purchase.order` | `purchase` | `state` | `button_confirm`, `action_create_invoice` |
| Entregas y recepciones | `stock.picking` | `stock` | `state` | `action_confirm`, `action_assign`, `button_validate` |
| Proceso de manufactura | `mrp.production` | `mrp` | `state` | `action_confirm`, `button_mark_done` |
| Ordenes de trabajo | `mrp.workorder` | `mrp` (con opcion activada) | `state` | `button_start`, `button_finish` |
| Facturacion a cliente | `account.move` (`move_type=out_invoice`) | `account` | `state` | `action_post` |
| Facturas de proveedor | `account.move` (`in_invoice`) | `account` | `state` | `action_post` |
| Cobros y pagos | `account.payment` | `account` | `state` | `action_post`, conciliacion |
| Oportunidades / CRM | `crm.lead` | `crm` | `stage_id` (no `state`) | cambio de etapa, `action_set_won_rainbowman` |
| Proyectos y tareas | `project.task` | `project` | `stage_id` | cambio de etapa |
| Punto de venta | `pos.order`, `pos.session` | `point_of_sale` | `state` | cierre de sesion |
| Ausencias | `hr.leave` | `hr_holidays` | `state` | `action_approve`, `action_refuse` |
| Gastos | `hr.expense.sheet` | `hr_expense` | `state` | `action_submit_sheet`, `action_approve_expense_sheets` |
| Reaprovisionamiento | `stock.warehouse.orderpoint`, `stock.rule` | `stock`, `purchase_stock`, `mrp` | - | `_run_pull`, `_run_buy`, `_run_manufacture` |
| Inventario valorado | `stock.valuation.layer` | `stock_account` | - | se crea al validar movimientos |

## Cuidado con los procesos que cruzan modulos

Las preguntas interesantes casi nunca caben en un modelo:

- **"Del pedido al cobro"**: `sale.order` -> `stock.picking` -> `account.move` ->
  `account.payment`. El pegamento son las rutas (`stock.rule`) y la politica de
  facturacion (`invoice_policy`).
- **"Como se abastece lo que vendo"**: la ruta del producto decide si nace una compra, una
  fabricacion o una salida de stock. Sin mirar `stock.rule` y las rutas del producto, la
  explicacion es incompleta.
- **"Por que no me deja validar"**: casi siempre es un `_constrains` o un `UserError` en
  el metodo del boton. Buscalo en la fuente antes de teorizar.

## Estados que no los pone un boton

Es la fuente de confusion numero uno para un administrador. Muchos estados son
**calculados**: `mrp.production.state` y `stock.picking.state` se derivan de sus
movimientos y de la reserva, no de una accion del usuario. Cuando documentes un ciclo de
vida, marca explicitamente que transiciones son un boton y cuales ocurren solas.

Buscalo asi:

```bash
python3 "$ODOO_EX/scripts/odoo_source.py" grep "_compute_state" --serie 18.0 --modules stock,mrp
```

## Donde mirar la personalizacion

Antes de dar por buena la explicacion estandar, comprueba que nadie la ha cambiado:

```bash
python3 "$ODOO_EX/scripts/odoo_probe.py" -i <slug> customizations --model <modelo>
```

Campos manuales (Studio), acciones de servidor, automatizaciones y crons sobre el modelo
raiz son exactamente lo que hace que la instancia del cliente no se comporte como el
manual.
