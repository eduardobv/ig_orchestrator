# renaming

@MODULE.md

Reglas rápidas:
- **El orden de llamadas al generador aleatorio es el de `sc2`** y vista previa = ejecución (misma semilla y reloj); no reordenar.
- **Renew (v4.17.0)**: casilla del editor (`AccountDraft.is_renew`) que pide solo la fecha del primer post. `planner.process_renew_tree` une los ficheros solo-id de `G:` con los descargados y los renombra como cuenta nueva (los de `G:` **en sitio**, irreversible: probar con copias); ignora cualquier otro nombre. Estado `RENEW`; necesita `G:` accesible y el Owner Id del catálogo. Sin columna nueva: se infiere de `rename_start_init_date`.
- Sin `G:` el renombrado sigue con el índice (`media_index`) y la cuenta queda `RENAMED_PENDING_MOVE`.
