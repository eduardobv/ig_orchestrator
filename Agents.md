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
Tarea 24 => v1.24.0
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
2. Importar JSON a SQLite.
3. Leer configuracion desde SQLite.
4. Para cada cuenta, crear carpetas.
5. Si `download_stories = true`, generar `https://www.instagram.com/stories/{username}/`.
6. Procesar primero stories.
7. Procesar despues las URLs manuales en orden.
8. Si una URL falla temporalmente, pasar a la siguiente y reintentar al final.
9. Si una URL falla con error definitivo, guardar error y no reintentar.
10. Mover archivos a carpeta correcta.
11. Generar reporte Markdown.

## Errores definitivos conocidos

No reintentar:

```text
We're sorry, we couldn't find that.
Stories for user_name not found
We can't get stories from a private account (instagram limit)
```

Guardar siempre el texto original.

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
