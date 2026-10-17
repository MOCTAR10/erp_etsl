#!/usr/bin/env python3
"""Hooks qualité Claude Code pour ETSL (déclarés dans .claude/settings.json).

- `post-edit` (PostToolUse sur Edit/Write/MultiEdit) : ruff (erreurs bloquantes : syntaxe, noms inconnus, imports
  manquants) sur le fichier Python modifié → retour immédiat à Claude au lieu d'un échec en CI.
- `stop` (fin de tâche) : tests backend impactés par le diff (`pytest --testmon`), puis typecheck frontend si des
  fichiers .ts/.tsx ont changé.

Code de sortie 2 = message renvoyé à Claude (qui corrige) ; 0 = silencieux.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # etls/
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def venv_python():
    for candidate in (BACKEND / ".venv" / "bin" / "python", BACKEND / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def run(cmd, cwd, timeout):
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 0, ""
    except FileNotFoundError:
        return 0, ""
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def fail(message):
    print(message[-4000:], file=sys.stderr)
    sys.exit(2)


def post_edit(payload):
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py"):
        return
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if BACKEND not in target.parents or "migrations" in target.parts:
        return
    code, out = run(
        [venv_python(), "-m", "ruff", "check", "--select", "E9,F63,F7,F82,F811", "--output-format", "concise", str(target)],
        BACKEND, 60,
    )
    if code != 0:
        fail(f"ruff a détecté une erreur bloquante dans {target.name} :\n{out}")


def changed_files():
    _, out = run(["git", "status", "--porcelain"], ROOT, 30)
    return [line[3:] for line in out.splitlines() if len(line) > 3]


def stop(payload):
    if payload.get("stop_hook_active"):  # déjà relancé par ce hook : ne pas boucler
        return
    files = changed_files()
    if any(f.startswith("backend/") and f.endswith(".py") for f in files):
        code, out = run([venv_python(), "-m", "pytest", "--testmon", "-q", "-x", "-p", "no:warnings"], BACKEND, 900)
        # 5 = aucun test sélectionné (rien d'impacté) : pas une erreur.
        if code not in (0, 5):
            fail(f"Tests impactés en échec (pytest --testmon) :\n{out}")
    if any(f.startswith("frontend/src/") and f.endswith((".ts", ".tsx")) for f in files):
        npx = "npx.cmd" if os.name == "nt" else "npx"
        code, out = run([npx, "tsc", "--noEmit", "-p", "."], FRONTEND, 300)
        if code != 0:
            fail(f"Typecheck frontend en échec :\n{out}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    {"post-edit": post_edit, "stop": stop}.get(mode, lambda p: None)(payload)


if __name__ == "__main__":
    main()
