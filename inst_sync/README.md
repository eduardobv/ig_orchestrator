# inst_sync · replicar el código en otra instancia (feat-uc4-7, dos partes desde v4.18.1)

**Parte 1 · en el PC principal**
1. Una vez: escribe en `destino.txt` la ruta del proyecto de la instancia vista desde este PC.
2. **Detén el batch** de la instancia.
3. Doble clic en `empujar.bat` (o `empujar.bat --simular`). Copia lo nuevo/cambiado de `src`, `tools`, `inst_sync`, `pyproject.toml` y `requirements.txt`, borra lo que ya no existe, guarda antes una copia de `src` en `bkp\` (las 3 últimas) e imprime las entradas de `CAMBIOS.md` posteriores a la versión de la instancia.
4. Al final dice si hace falta la parte 2. Si no hay nada que copiar: «Instancia sincronizada con el PC».

**Parte 2 · en la instancia (solo si la parte 1 lo pide)**
Doble clic en `sincronizar.bat`: instala `requirements.txt` si cambió o falta `cryptg`, aplica los `sql\*.sql` pendientes (con copia de la base) y abre la base para migrar el esquema.

Nunca toca: `.env`, `data`, `logs`, `reports`, `config`, `.venv`, `*.session*`, `origen.txt`, `destino.txt`, `empujar.bat`, `estado.json` ni `bkp`. Los SQL no se ejecutan por red (la base usa WAL).

Para el mantenedor: cada feat que requiera un paso manual añade una entrada a `CAMBIOS.md`; un cambio de datos puntual va como `sql\NNN_nombre.sql`.
