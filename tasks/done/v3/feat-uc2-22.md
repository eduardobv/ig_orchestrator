# feat-uc2-22 · Informe de Stories Inbox

## Objetivo
La modal Stories Inbox mostraba un log con cada fichero. Ahora muestra solo lo útil: total movido, problemas, sobrantes en la carpeta y forzar mover.

## Resultado de la implementación
* `filesystem/story_inbox.py`: estado `OVERWRITTEN`, `StoryInboxReport`, `build_report` (re-escanea el inbox), `force_move_conflicts` y `overwrite` en `_move_one`.
* `gui/stories/dialog.py`: banner verde/ámbar, tabla de problemas, lista de sobrantes, botón *Forzar mover (sobrescribir)* con confirmación; claves i18n `stories.*` (es/en).
* Pruebas: `tests/filesystem/test_story_inbox_report.py`, `tests/gui/test_stories_report_dialog.py`.

## No se hizo
* Forzar mover solo cubre duplicados (`DESTINATION_EXISTS`); los demás problemas requieren corregir catálogo/carpeta. Sin reintento selectivo por fila.
* No probado con la carpeta real de stories.
