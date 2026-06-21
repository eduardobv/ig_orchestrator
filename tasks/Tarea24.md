# Tarea 24 - Identidad de lotes, ejecucion combinada e historico de cuentas

Version objetivo: `v1.24.0`

## Objetivo

Hacer que cada `batch_name` represente una importacion unica, permitir combinar
un lote nuevo con la continuacion de otro lote pendiente, mantener un historico
global de usernames y convertir `batch.json` en una plantilla reutilizable tras
crear un backup.

## Alcance

* Rechazar en `--run` cualquier `batch_name` ya existente.
* Mantener `run_continue --batch-id/--batch-name`.
* Agregar `--join-after-pending-batch-id` y
  `--join-before-pending-batch-id`.
* Crear y poblar `account_history`.
* Ignorar usernames vacios, URLs vacias y cuentas sin trabajo.
* Crear `config/bkp/{batch_name}_batch.json` y limpiar el JSON importado.
* Mostrar progreso compacto por cuenta.
* Actualizar README, Agents, PLAN, CHANGELOG y tests.

## Pruebas

* Parser de entradas reutilizables.
* Unicidad de lotes en SQLite e importador.
* Historico global de cuentas.
* Backup y limpieza del JSON.
* Orden de ejecucion de modos join.
* Callback de progreso por cuenta.
