# inst_sync · replicar el código en otra instancia (feat-uc4-7)

1. Una vez, en la instancia: copia esta carpeta `inst_sync` y escribe en `origen.txt` la ruta del
   proyecto del PC principal.
2. **Detén el batch** de la instancia.
3. Doble clic en `sincronizar.bat` (o `sincronizar.bat --simular` para ver qué haría).

Qué hace: copia lo nuevo/cambiado de `src`, `tools`, `inst_sync`, `pyproject.toml` y
`requirements.txt`; borra lo que ya no existe en el origen; guarda antes una copia de `src` en
`bkp\` (las 3 últimas); instala `requirements.txt` si cambió o falta `cryptg`; aplica los `sql\*.sql`
pendientes (con copia de la base); abre la base para migrar el esquema; muestra las entradas de
`CAMBIOS.md` posteriores a tu versión.

Nunca toca: `.env`, `data`, `logs`, `reports`, `config`, `.venv`, `*.session*`, `origen.txt`,
`estado.json`, `bkp` ni `sincronizar.bat` (si cambia el lanzador, cópialo a mano).

Para el mantenedor: cada feat que requiera un paso manual añade una entrada a `CAMBIOS.md`; un
cambio de datos puntual va como `sql\NNN_nombre.sql`.
