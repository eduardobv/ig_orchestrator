# Patch v1.26.9 - Contexto de lote nuevo y lote registrado

## Objetivo

Evitar que las cuentas preparadas para un lote nuevo actualicen por accidente
un borrador recuperado anteriormente desde SQLite.

## Cambios

* La cabecera muestra siempre si se trabaja en un lote nuevo, en un lote
  registrado editable o en un lote cuya ejecución ya comenzó.
* `Registrar lote nuevo` cambia a `Actualizar lote` al recuperar o registrar un
  borrador y muestra su nombre e ID.
* `Nuevo lote` desvincula el batch abierto, vacía las cuentas y el editor y
  genera un nombre nuevo sin modificar el lote anterior en SQLite.
* `Limpiar lote` se sustituye por `Eliminar todo`.
* En un lote registrado, `Eliminar todo` confirma con el nombre y el ID y
  recuerda que hay que pulsar `Actualizar lote` para persistir el cambio.
* Un borrador ya registrado puede guardarse sin cuentas después de
  `Eliminar todo`, pero nunca se puede ejecutar vacío.
* Un lote cuya ejecución ya comenzó queda identificado como no editable; para
  preparar otro se debe pulsar `Nuevo lote`.

## Persistencia

No se agregan tablas ni migraciones. La identidad editable continúa siendo
`input_batches.id`; el cambio impide reutilizar ese ID cuando el usuario cambia
explícitamente al modo de lote nuevo. Los drafts vacíos se conservan como
`DRAFT` y siguen siendo recuperables.

## Pruebas

Se cubren las etiquetas y acciones disponibles en cada contexto, la
desvinculación de IDs al crear un lote nuevo y el aviso de eliminación total
para un lote registrado.
