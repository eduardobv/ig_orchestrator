"""Sync an instance with the main PC code (feat-uc4-7, two parts since v4.18.1).

Part 1 · ``--empujar`` (``empujar.bat``, run on the main PC): mirrors ``src``, ``tools``,
``inst_sync`` and the dependency files into the instance folder reachable by network (file copies
only, no Python and no database of the instance are touched) and says whether part 2 is needed.

Part 2 · no flag (``sincronizar.bat``, run on the instance): installs ``requirements.txt`` when it
changed (or ``cryptg`` is missing), applies pending ``sql/*.sql`` once each and opens the GUI
database so schema migrations run.

Never touches instance-owned data: ``.env``, ``data``, ``logs``, ``reports``, ``config``,
``.venv``, ``*.session*`` (they are simply not in the mirrored set). Standard library only.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MIRROR_DIRS = ("src", "tools", "inst_sync")
MIRROR_FILES = ("pyproject.toml", "requirements.txt")
# Relative to the ``inst_sync`` folder: owned by one side, never copied nor deleted.
KEEP_IN_SYNC_DIR = {"origen.txt", "destino.txt", "empujar.bat", "estado.json", "bkp"}
SKIP_DIR_NAMES = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
GUI_DB = Path("data") / "orchestrator_gui.sqlite"
BACKUPS_TO_KEEP = 3
VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
HEADING_RE = re.compile(r"^##\s+v?(\d+\.\d+\.\d+)\b.*$", re.MULTILINE)
MAX_LISTED = 15


def _skip(rel: Path, top: str) -> bool:
    if any(part in SKIP_DIR_NAMES for part in rel.parts) or rel.suffix in SKIP_SUFFIXES:
        return True
    return top == "inst_sync" and bool(rel.parts) and rel.parts[0] in KEEP_IN_SYNC_DIR


def _files(root: Path, top: str) -> dict[Path, Path]:
    """Relative path -> absolute path of the mirrored files under ``root/top``."""
    base = root / top
    if not base.is_dir():
        return {}
    return {
        p.relative_to(base): p
        for p in base.rglob("*")
        if p.is_file() and not _skip(p.relative_to(base), top)
    }


def plan_mirror(source: Path, target: Path) -> dict[str, list[Path]]:
    """Return ``{"copy": [...], "delete": [...]}`` with paths relative to the project root."""
    filecmp.clear_cache()  # the cache keys on size+mtime: stale hits hide quick same-size rewrites
    copy: list[Path] = []
    delete: list[Path] = []
    for top in MIRROR_DIRS:
        src_files = _files(source, top)
        dst_files = _files(target, top)
        for rel, src_path in src_files.items():
            dst_path = dst_files.get(rel)
            if dst_path is None or not filecmp.cmp(src_path, dst_path, shallow=False):
                copy.append(Path(top) / rel)
        delete.extend(Path(top) / rel for rel in dst_files if rel not in src_files)
    for name in MIRROR_FILES:
        src_path, dst_path = source / name, target / name
        if src_path.is_file() and (not dst_path.is_file() or not filecmp.cmp(src_path, dst_path, shallow=False)):
            copy.append(Path(name))
    return {"copy": sorted(copy), "delete": sorted(delete)}


def apply_mirror(source: Path, target: Path, plan: dict[str, list[Path]]) -> None:
    for rel in plan["copy"]:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dest)
    for rel in plan["delete"]:
        (target / rel).unlink(missing_ok=True)
    for top in MIRROR_DIRS:  # drop directories left empty by the deletions
        base = target / top
        for folder in sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True):
            if not any(folder.iterdir()):
                folder.rmdir()


def backup_code(target: Path, version: str, now: datetime) -> Path | None:
    """Copy the current ``src`` to ``inst_sync/bkp`` and keep the newest few."""
    src = target / "src"
    if not src.is_dir():
        return None
    bkp_root = target / "inst_sync" / "bkp"
    bkp_root.mkdir(parents=True, exist_ok=True)
    dest = bkp_root / f"src_{version}_{now:%Y%m%d_%H%M%S}"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for old in sorted(p for p in bkp_root.iterdir() if p.is_dir() and p.name.startswith("src_"))[:-BACKUPS_TO_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def installed_version(target: Path) -> str:
    init = target / "src" / "ig_orchestrator" / "__init__.py"
    match = VERSION_RE.search(init.read_text(encoding="utf-8")) if init.is_file() else None
    return match.group(1) if match else "0.0.0"


def _vtuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def pending_changes(cambios_text: str, since: str) -> list[tuple[str, str]]:
    """``CAMBIOS.md`` entries (newest first) strictly newer than ``since``."""
    matches = list(HEADING_RE.finditer(cambios_text))
    entries = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cambios_text)
        entries.append((match.group(1), cambios_text[match.start():end].strip()))
    return [(v, body) for v, body in entries if _vtuple(v) > _vtuple(since)]


def pending_sql(sql_dir: Path, applied: list[str]) -> list[Path]:
    if not sql_dir.is_dir():
        return []
    return [p for p in sorted(sql_dir.glob("*.sql")) if p.name not in applied]


def apply_sql(db_path: Path, scripts: list[Path]) -> list[str]:
    done: list[str] = []
    with sqlite3.connect(db_path) as connection:
        for script in scripts:
            connection.executescript(script.read_text(encoding="utf-8"))
            done.append(script.name)
    return done


def instance_pending(target: Path, state: dict) -> list[str]:
    """Reasons why part 2 (``sincronizar.bat`` on the instance) is needed; empty when it is not."""
    reasons = []
    if file_sha(target / "requirements.txt") != state.get("requirements_sha", ""):
        reasons.append("instalar las dependencias (requirements.txt)")
    scripts = pending_sql(target / "inst_sync" / "sql", state.get("sql_applied", []))
    if scripts:
        reasons.append("aplicar SQL: " + ", ".join(s.name for s in scripts))
    return reasons


def read_destination(inst_dir: Path, cli_value: str | None) -> Path:
    """Instance folder as seen from the main PC: ``--destino`` or the first line of ``destino.txt``."""
    if cli_value:
        return Path(cli_value)
    path_file = inst_dir / "destino.txt"
    if path_file.is_file():
        for line in path_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return Path(line)
    raise SystemExit(
        "Falta la carpeta de la instancia. Escribe su ruta en inst_sync\\destino.txt "
        "(una línea, p. ej. \\\\INST1\\ig_orchestrator) o usa --destino."
    )


def _same_folder(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return a == b


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _run_python(target: Path, code: str) -> subprocess.CompletedProcess:
    env_path = str(target / "src")
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=target,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": env_path},
    )


def _confirm_stopped(args, where: str) -> bool:
    if args.si or input(f"¿Está detenido el batch en {where}? (s/N) ").strip().lower() in {"s", "si", "sí", "y"}:
        return True
    print("Cancelado. Detén el batch y vuelve a ejecutar.")
    return False


def _print_changes(cambios: Path, since: str) -> None:
    news = pending_changes(cambios.read_text(encoding="utf-8"), since) if cambios.is_file() else []
    if news:
        print("\n=== Cambios desde la versión de la instancia (léelos por si piden algún paso manual) ===")
        for _, body in news:
            print(body + "\n")


def run_push(args, inst_dir: Path) -> int:
    """Part 1, on the main PC: copy the code into the instance folder and say whether part 2 is needed."""
    source = Path(args.origen).resolve() if args.origen else inst_dir.parent
    target = read_destination(inst_dir, args.destino).resolve()
    if not (source / "src" / "ig_orchestrator").is_dir():
        print(f"ERROR: {source} no parece un proyecto ig_orchestrator.")
        return 2
    if not (target / "src" / "ig_orchestrator").is_dir():
        print(f"ERROR: {target} no parece un proyecto ig_orchestrator (¿ruta de red accesible?).")
        return 2
    if _same_folder(source, target):
        print("ERROR: la carpeta de la instancia es la de este PC (revisa inst_sync\\destino.txt).")
        return 2

    state_path = target / "inst_sync" / "estado.json"
    state = _load_state(state_path)
    before, pc_version = installed_version(target), installed_version(source)
    plan = plan_mirror(source, target)

    print(f"PC     : {source} (v{pc_version})\nInst.  : {target} (v{before})")
    print(f"Ficheros a copiar: {len(plan['copy'])} · a borrar: {len(plan['delete'])}")
    for label, items in (("copiar", plan["copy"]), ("borrar", plan["delete"])):
        for rel in items[:MAX_LISTED]:
            print(f"  - {label} {rel}")
        if len(items) > MAX_LISTED:
            print(f"  … y {len(items) - MAX_LISTED} más a {label}")

    if not plan["copy"] and not plan["delete"]:
        reasons = instance_pending(target, state)
        if reasons:
            print("El código ya está copiado, pero falta la parte 2: ejecuta inst_sync\\sincronizar.bat EN LA INSTANCIA para "
                  + "; ".join(reasons) + ".")
        else:
            print(f"Instancia sincronizada con el PC (v{before}). No hay nada que hacer.")
        return 0
    if args.simular:
        print("Simulación: no se ha cambiado nada.")
        return 0
    if not _confirm_stopped(args, "la instancia"):
        return 1

    backup = backup_code(target, before, datetime.now())
    apply_mirror(source, target, plan)
    after = installed_version(target)
    print(f"Código copiado ({before} -> {after}). Copia anterior: {backup}")
    _print_changes(target / "inst_sync" / "CAMBIOS.md", state.get("version", before))
    state["version"] = after
    _save_state(state_path, state)

    reasons = instance_pending(target, state)
    if reasons:
        print("PARTE 2 NECESARIA: ejecuta inst_sync\\sincronizar.bat EN LA INSTANCIA para " + "; ".join(reasons) + ".")
    else:
        print("No hace falta ejecutar nada en la instancia (la base se migra sola al abrir la app).")
    return 0


def run_local(args, inst_dir: Path) -> int:
    """Part 2, on the instance: what needs its own Python and database."""
    target = Path(args.destino).resolve() if args.destino else inst_dir.parent
    if not (target / "src" / "ig_orchestrator").is_dir():
        print(f"ERROR: {target} no parece un proyecto ig_orchestrator.")
        return 2
    state_path = target / "inst_sync" / "estado.json"
    state = _load_state(state_path)
    reasons = instance_pending(target, state)
    req_changed = file_sha(target / "requirements.txt") != state.get("requirements_sha", "")
    scripts = pending_sql(target / "inst_sync" / "sql", state.get("sql_applied", []))

    print(f"Instancia: {target} (v{installed_version(target)})")
    print(f"Pendiente: {'; '.join(reasons) if reasons else 'nada (solo se comprueba cryptg y se abre la base)'}")
    if args.simular:
        print("Simulación: no se ha cambiado nada.")
        return 0
    if not _confirm_stopped(args, "esta instancia"):
        return 1

    cryptg_ok = _run_python(target, "import cryptg").returncode == 0
    if req_changed or not cryptg_ok:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(target / "requirements.txt")])
        if result.returncode != 0:
            print("ERROR: falló pip. Revisa el mensaje y vuelve a ejecutar.")
            return 3
        cryptg_ok = _run_python(target, "import cryptg").returncode == 0
    state["requirements_sha"] = file_sha(target / "requirements.txt")
    print(f"cryptg (descarga rápida de Telegram): {'OK' if cryptg_ok else 'FALTA'}")

    db_path = target / GUI_DB
    if scripts and db_path.is_file():
        now = datetime.now()
        db_backup = db_path.with_name(f"{db_path.stem}_pre_sync_{now:%Y%m%d_%H%M%S}{db_path.suffix}")
        (target / "inst_sync" / "bkp").mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, target / "inst_sync" / "bkp" / db_backup.name)
        state["sql_applied"] = state.get("sql_applied", []) + apply_sql(db_path, scripts)
        print(f"SQL aplicados: {', '.join(s.name for s in scripts)}")
    if db_path.is_file():
        migrated = _run_python(
            target,
            "from ig_orchestrator.db.gui_migrations import prepare_sqlite; "
            f"prepare_sqlite(r'{db_path}')",
        )
        print("Migraciones de la base: " + ("OK" if migrated.returncode == 0 else f"ERROR\n{migrated.stderr}"))
    state["version"] = installed_version(target)
    _save_state(state_path, state)
    print("Listo. La instancia está al día y ya puedes abrir la app.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sincroniza una instancia con el PC principal (dos partes).")
    parser.add_argument("--empujar", action="store_true", help="Parte 1 (en el PC): copia el código a la instancia.")
    parser.add_argument("--origen", help="Parte 1: carpeta del proyecto en este PC (por defecto, la del script).")
    parser.add_argument("--destino", help="Parte 1: carpeta de la instancia (por defecto, destino.txt). "
                                          "Parte 2: carpeta de la instancia (por defecto, la del script).")
    parser.add_argument("--simular", action="store_true", help="Solo muestra lo que haría.")
    parser.add_argument("--si", action="store_true", help="No pedir confirmación.")
    args = parser.parse_args(argv)
    inst_dir = Path(__file__).resolve().parent
    return run_push(args, inst_dir) if args.empujar else run_local(args, inst_dir)


if __name__ == "__main__":
    raise SystemExit(main())
