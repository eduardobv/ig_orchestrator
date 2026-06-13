# Copilot Instructions

Read `PLAN.md`, `Agents.md`, and the active `tasks/TareaX.md` before implementing.

Versioning maps each task to its own minor: `Tarea1.md` targets `v1.1.0`, `Tarea2.md` targets `v1.2.0`, and so on through `Tarea24.md` targeting `v1.24.0`. Fixes within the same task increment the patch, for example `v1.1.1`.

Do not implement rename integration, duplicate cleanup from the rename process, final move to `G:\4K Stogram`, or a UI in `v1.0.1`.

SQLite is the source of truth after importing the JSON batch. Keep modules small, testable, Windows-compatible, and update `CHANGELOG.md` for every task.

Final implementation responses should include suggested `git commit` and `git tag` commands for the target version.
