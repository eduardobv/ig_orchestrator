# T2.RELEASE — PR a master y tag v2.0.0

Estado: **PENDIENTE**. No abrir PR ni crear el tag hasta que el usuario
confirme que el flujo GUI v2 está validado.

## Cómo pedir esta tarea (otra sesión)

Cualquiera de estas frases basta:

* «Ejecuta la tarea pendiente»
* «Ejecuta el release v2»
* «Ejecuta `tasks/Tarea_v2_0_0_release.md`»

Leer antes: `Agents.md`, este archivo, `CHANGELOG.md` (bloque Unreleased).

## Contexto

* Rama de trabajo: `v2/orchestrator` (tracking `origin/v2/orchestrator`).
* Destino: `master` (`origin/master`).
* Tag a crear: `v2.0.0`.
* Tag de rollback (no mover): `v1.31.0` = mismo commit que `master` actual
  (`a89243d feat: implement tarea GUI 3 leftover rename, catalogo del dia y cola de lotes`).
* Remoto: `git@github.com:eduardobv/ig_orchestrator.git`.
* Compare URL:
  `https://github.com/eduardobv/ig_orchestrator/compare/master...v2/orchestrator?expand=1`

`gh` puede no estar instalado en Windows. Si falta, crear la PR por la
URL de compare o instalar GitHub CLI; no inventar un merge local como
sustituto de la PR.

## Precondiciones (obligatorias)

1. El usuario ha confirmado la validación del flujo, o ha pedido
   explícitamente ejecutar esta tarea.
2. Working tree limpio salvo el commit de cierre de CHANGELOG de este
   procedimiento. Si hay otros cambios, preguntar; no mezclarlos.
3. `git fetch origin` y comprobar que `v2/orchestrator` incluye los
   arreglos validados (fuente Segoe UI, log al renombrar, y cualquier
   fix posterior).
4. Tag `v1.31.0` existe y no se mueve.
5. No commitear `.env`, `*.session`, `*.session-journal` ni bases SQLite
   reales (`data/orchestrator.sqlite`, `data/orchestrator_gui.sqlite`,
   copias en `data/old/`).

Si el usuario **no** ha validado todavía: no ejecutar. Recordar este
archivo y parar.

## Fuera de alcance

* Rediseñar el diálogo Lotes / ejecuciones.
* Escribir en `data/orchestrator.sqlite`.
* Migrar lotes, URLs o ficheros de v1.
* Force-push a `master` o a `v1.31.0`.
* Tag `v2.0.0` si `pytest` falla.

## Pasos (ejecutar en orden)

### 1. Cerrar CHANGELOG

En `CHANGELOG.md`, el bloque:

```text
## Unreleased - v2.0.0 (en progreso)
Fecha: 2026-08-22
```

pasa a:

```text
## v2.0.0 - GUI, sqlite v2 y aviso Telegram
Fecha: YYYY-MM-DD
```

Usar la fecha del día del release. Añadir al final de ese bloque, en
Pruebas ejecutadas, la corrida de pytest de este procedimiento.

No reescribir el historial de `v1.31.0`.

### 2. Tests

```bash
python -m pytest -q
```

Debe pasar entero. Si falla, no PR ni tag.

### 3. Commit de cierre y push de la rama

```bash
git checkout v2/orchestrator
git add CHANGELOG.md
git commit -m "chore: close changelog for v2.0.0"
git push origin v2/orchestrator
```

Si este archivo de tarea u `Agents.md` no están en `origin`, incluirlos
en el mismo commit (o en uno inmediatamente anterior).

### 4. Abrir PR a master

Título:

```text
feat: Instagram Orchestrator v2.0.0
```

Cuerpo mínimo:

```text
GUI v2, SQLite `orchestrator_gui.sqlite` (user_version 100), avisos Telegram.

Rollback: `git checkout v1.31.0` + `data/orchestrator.sqlite`.
El diálogo Lotes no se rediseña.

Closes the v2.0.0 series on branch v2/orchestrator.
```

Crear la PR (preferir merge commit, **no squash**, para que `v1.31.0`
siga siendo ancestro claro):

```bash
gh pr create --base master --head v2/orchestrator --title "feat: Instagram Orchestrator v2.0.0" --body "..."
```

Si `gh` no existe: abrir la compare URL, crear la PR a mano, y dejar el
enlace en la respuesta. No fusionar por `git merge` local salvo que el
usuario lo pida porque GitHub no está disponible.

### 5. Merge

Cuando la PR esté abierta y el usuario no haya pedido dejarla sin
fusionar:

```bash
gh pr merge --merge
```

Después:

```bash
git checkout master
git pull origin master
```

Comprobar que `master` incluye el cierre de CHANGELOG y que
`git merge-base --is-ancestor v1.31.0 master` es cierto.

### 6. Tag anotado y push

El tag apunta al commit de `master` ya fusionado, no a un tip suelto de
la rama si el merge creó un merge commit.

```bash
git checkout master
git pull origin master
git tag -a v2.0.0 -m "Instagram Orchestrator v2.0.0"
git push origin v2.0.0
```

No usar `git tag -f`. Si `v2.0.0` ya existiera, parar y preguntar.

### 7. Verificar

```bash
git log -1 --oneline master
git show -s --format="%H %D" v2.0.0
git ls-remote --tags origin v2.0.0
python -m pytest -q
```

Rollback documentado (no ejecutarlo en esta tarea):

```text
git checkout v1.31.0
```

más el `.env` original y `data/orchestrator.sqlite`. La GUI v2 usa
`data/orchestrator_gui.sqlite` y no debe haber escrito el SQLite v1.

### 8. Marcar esta tarea

Al terminar, añadir al final de este archivo:

```text
## Hecho
Fecha: YYYY-MM-DD
PR: <url>
Tag: v2.0.0 en <sha>
```

Commit de ese apunte en `master` o en un patch posterior; no retaguear.

## Respuesta final esperada

* URL de la PR.
* SHA de `master` y del tag `v2.0.0`.
* Resultado de `python -m pytest -q`.
* Recordatorio de rollback: `git checkout v1.31.0`.
