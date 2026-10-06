# Patch v1.26.7 - Maestro de lotes y cierre manual

## Objetivo

Separar los lotes guardados de las ejecuciones, permitir administrar borradores
para lanzarlos más tarde y evitar que una URL sin respuesta bloquee un lote.

## Cambios

* El catálogo abre Instagram con doble click además del menú `Abrir`.
* `Registrar lote` crea un batch `DRAFT`, editable y borrable desde el maestro
  `Lotes / ejecuciones`.
* Al ejecutar, el batch cambia a `IMPORTED` y ya no admite edición.
* Una respuesta completamente ausente se registra como `NO_BOT_RESPONSE`, se
  reintenta por rondas y termina `FAILED_FINAL` al agotar el máximo.
* Tras cancelar, `Completar` cierra manualmente una cuenta sin borrar su
  trazabilidad.
* `Renombrar` se habilita cuando todas las cuentas de una ejecución real se han
  completado, incluidas las completadas manualmente.

## Persistencia

No se agregan tablas. `DRAFT` se incorpora a los estados textuales de
`input_batches`; las bases existentes son compatibles sin migración destructiva.

## Pruebas

Se cubren creación, recuperación, actualización, bloqueo y borrado de drafts;
finalización manual; habilitación de renombrado; y clasificación del silencio
del bot.
