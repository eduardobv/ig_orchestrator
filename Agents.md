# Agents.md

## Proposito

Este archivo sirve como instrucciones base para cualquier IA que implemente tareas de este proyecto.

Cuando se pida implementar una tarea, leer primero:

1. `PLAN.md`
2. `Agents.md`
3. `tasks/TareaX.md`
4. El codigo existente relacionado

La IA debe implementar solo la tarea solicitada, salvo que sea imprescindible tocar soporte comun.

## Version activa

La version activa se organiza por tarea.

Cada tarea principal genera un minor:

```text
Tarea 1  => v1.1.0
Tarea 2  => v1.2.0
...
Tarea 23 => v1.23.0
```

Los arreglos de una tarea incrementan el patch:

```text
v1.1.1, v1.1.2, ...
v1.2.1, v1.2.2, ...
```

Objetivo general de la serie `v1.x`: estabilizar descarga, persistencia, reintentos y reportes.

No implementar en `v1.0.1`:

* integracion con el script de renombrado;
* limpieza de duplicados generados por el renombrador;
* movimiento final a `G:\4K Stogram`;
* UI web o standalone.

## Reglas de arquitectura

* Usar Python 3.11+.
* Mantener modulos pequenos y testeables.
* Separar CLI, servicios de aplicacion, repositorios, modelos, Telegram, filesystem y reportes.
* SQLite es la fuente de verdad tras importar el JSON.
* El JSON solo sirve para cargar datos iniciales.
* La futura UI debe poder escribir los mismos datos que hoy escribe el importador JSON.
* Evitar dependencias nuevas si no aportan una mejora clara.
* Usar `pathlib.Path` para rutas.

## Seguridad

* No commitear `.env`.
* No commitear `*.session` ni `*.session-journal`.
* No commitear bases SQLite reales.
* No loguear `api_hash`, codigos de login ni secretos.
* No borrar archivos automaticamente en `v1.0.1`.

## Persistencia y trazabilidad

* Cada invocacion del programa usa una sola carpeta
  `logs/YYYYMMDD_HHMMSS`, fijada al inicio de la ejecucion.
* Todas las cuentas, batches unidos y reintentos de esa invocacion escriben
  dentro de esa misma carpeta; nunca calcular otra carpeta desde el inicio de
  un run de cuenta.
* `input_batches.batch_name` es unico y no se reutiliza.
* `--run` siempre importa un lote nuevo; para continuar uno existente se usa
  `run_continue` o los modos join con un `batch_id` pendiente.
* Tras importar correctamente un lote real, respaldar el JSON en `config/bkp`
  y limpiar sus URLs sin perder `username` ni `start_now_date`.
* `account_history` conserva usernames globales sin repetir entre lotes.

Cada URL debe guardar:

* URL original;
* tipo clasificado;
* origen (`GENERATED_STORY` o `INPUT_URL`);
* estado;
* mensaje enviado al bot si aplica;
* error original si falla;
* tipo de error;
* contador de reintentos;
* archivos asociados;
* timestamps.

Cada ejecucion debe poder reconstruirse desde SQLite y generar un reporte Markdown.

## Flujo v1.0.1

1. Inicializar SQLite si hace falta.
2. Leer y validar el JSON.
3. Antes de importar, ordenar las cuentas en memoria: primero las que solo
   descargan stories y despues de menos a mas URLs, conservando los empates.
4. Importar el lote ordenado a SQLite.
5. Leer configuracion desde SQLite.
6. Para cada cuenta, crear carpetas.
7. Si `download_stories = true`, generar `https://www.instagram.com/stories/{username}/`.
8. Procesar primero stories.
9. Procesar despues las URLs manuales en orden.
10. Si una URL falla temporalmente, pasar a la siguiente y reintentar al final.
11. Si una URL falla con error definitivo, guardar error y no reintentar.
12. Mover archivos a carpeta correcta.
13. Generar reporte Markdown.

## Errores definitivos conocidos

No reintentar:

```text
We're sorry, we couldn't find that.
Stories for {username} not found
We can't get stories from a private account (instagram limit)
```

Guardar siempre el texto original.

El error de stories debe detectarse por patron, porque `{username}` cambia en
cada respuesta. En respuestas mixtas de stories se deben conservar todos los
videos y todas las fotos; la presencia de un documento con nombre no invalida
las fotos sin nombre original.

## Reintentos

Los reintentos son por ronda, no inmediatos mientras queden URLs nuevas.

La cola de reintentos es FIFO.

Tras agotar `MAX_RETRIES`, marcar `FAILED_FINAL`.

## Tests

Cada tarea debe incluir tests cuando toque logica nueva.

Preferir tests unitarios para parsers, clasificadores y politicas.

Usar SQLite temporal en tests de repositorios.

No depender de Telegram real en tests automatizados.

## CHANGELOG

Cada tarea debe actualizar `CHANGELOG.md` con:

* version/tarea;
* fecha;
* archivos creados;
* archivos modificados;
* resumen de comportamiento agregado;
* pruebas ejecutadas.

Si `CHANGELOG.md` no existe, crearlo.

## Respuesta final de cada implementacion

Al terminar una tarea o patch, responder con:

* resumen breve de cambios;
* pruebas ejecutadas;
* comando sugerido de commit;
* comando sugerido de tag.

Formato recomendado:

```bash
git add .
git commit -m "feat: implement tarea X ..."
git tag v1.X.0
```

Para arreglos de una tarea ya implementada:

```bash
git add .
git commit -m "fix: adjust tarea X ..."
git tag v1.X.1
```

## Estilo de implementacion

* Implementar una tarea cada vez.
* No mezclar refactors grandes con la tarea.
* No cambiar APIs existentes sin actualizar tests y documentacion.
* No introducir comportamiento futuro salvo que este explicitamente pedido.
* Mantener mensajes de error claros y accionables.
* Preservar informacion existente en SQLite.
