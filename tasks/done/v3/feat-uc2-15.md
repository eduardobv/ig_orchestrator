# feat-uc2-15 — El estado también sigue a las carpetas `-Inactive` (v3.15.0)

Feat incremental de v3 (catálogo, UC2): completa `feat-uc2-14`, que solo cubría `-Deleted`.

## Qué se hizo

Al **mover** (no renombrar) cuentas, o una carpeta con cuentas, desde la app:

| Destino | Resultado |
|---|---|
| Carpeta `…-Deleted` / carpeta de eliminadas | **Eliminada** (como en v3.14) |
| Carpeta `…-Inactive` (también `-Inactiva`/`-Inactivo`) y la cuenta no es Inactiva | **Inactiva** (si estaba Eliminada, deja de estarlo) |
| Carpeta normal, viniendo de `-Deleted` o `-Inactive` | Vuelve al estado que tenía **antes** (o Activa si no se conoce) |

- La reactivación ahora depende de **de dónde viene** la cuenta (no solo de su estado): una cuenta Inactiva manualmente que se mueve entre carpetas normales sigue Inactiva.
- La vista previa del plan muestra «Estado: @cuenta → Inactiva» (además de Eliminada/Reactivada) y **Deshacer** lo revierte.
- El color de las Inactivas es el ya configurado para *Inactivo*.

## No incluido

- Renombrar una carpeta a `…-Inactive`/`…-Deleted` no cambia estados.
- Mover con el Explorador no cambia estados (la sincronización solo informa).

## Pruebas

`tests/library/test_status_follows_folder.py`: entrar/salir de `-Inactive` (estado previo), inactiva manual entre carpetas normales, de `-Deleted` a `-Inactive` y viceversa, deshacer.
