# feat-uc2-16 — Cierre de pendientes de v3 (v3.16.0)

Feat incremental de v3 que cierra los pendientes que quedaban en `docs/arquitectura-v3.md` §8 y que se podían resolver sin `G:` real.

## a) Eliminar carpeta vacía

Menú contextual de carpeta → **Eliminar carpeta vacía…** (`FsOperationService.plan_delete_empty_folder`). Solo si la carpeta (y sus subcarpetas) **no tienen ficheros** y **no contienen cuentas** del catálogo; si no, el plan queda bloqueado y explica por qué (`NOT_EMPTY`, `HAS_ACCOUNTS`). Un `RMDIR` por carpeta (la más profunda primero), con vista previa y **Deshacer** (recrea las carpetas). Se corrigió `can_undo` para deshacer un `RMDIR`.

## b) Papelera

- **Retención** en Ajustes → Catálogo (`trash.retention_days`, 0 = sin límite): fija la fecha de caducidad de lo que entra en la papelera. La papelera muestra la columna *Caduca*, un contador de caducadas, **Vaciar caducadas…** (sigue exigiendo escribir `ELIMINAR`) y al arrancar avisa en la consola. **Nunca borra sola.**
- **Quitar también del catálogo:** tras el borrado definitivo pregunta si quitar las cuentas del catálogo (`TrashService.remove_from_catalog`): se borran sus filas (y su índice/historial); las que están en un lote o aún tienen otra copia en la papelera se conservan.

## c) Auditoría del índice

`Auditar biblioteca…` añade `INDEX_MISSING` (la cuenta tiene ficheros según sus contadores y ninguno en el índice) e `INDEX_STALE` (un contador difiere del número de ficheros indexados de esa subcarpeta).

## d) Almacén visible

La barra de estado muestra `Almacén: N cuenta(s) · tamaño pendientes` (y `· G: desconectada`), se actualiza tras renombrar y volcar; al arrancar con `G:` conectada y cuentas pendientes lo indica en la consola.

## No incluido (decisiones)

- **Fusión genérica carpeta↔carpeta:** se descarta por riesgo (mover cuentas dentro de grupos que se fusionan exige reasignar filas del catálogo); la fusión de cuentas sigue en «Cambió de username…» (feat 7).
- Almacén con estructura plana (`flat`): sin valor claro frente a la réplica de la biblioteca.
- Segundo renombrado de una cuenta nueva ya almacenada (queda sin ruta hasta volcar).
- Pestaña persistente de resultados del renombrado; `compareProcess` de sc2 (feat propio si se quiere).
- Probar con `G:` real y arrastrar con ratón real: requieren tu entorno.

## Pruebas

`tests/library/test_delete_empty_folder.py`, `tests/library/test_trash_retention_audit_index.py`, `tests/staging/test_staging.py` (texto de la barra de estado) y comprobación con la app real de la barra de estado.
