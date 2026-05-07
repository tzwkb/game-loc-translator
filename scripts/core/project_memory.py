"""
project_memory.py — Agent-level project memory.
Reads/writes workspace/project_profiles.json for persistent project settings.
"""

import json
from pathlib import Path
import config

PROFILE_PATH = config.WORKSPACE_DIR / "project_profiles.json"


def _load() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return {}


def _save(data: dict):
    PROFILE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_profile(project_id: str) -> dict | None:
    """Get stored profile for a project. Returns None if not found."""
    return _load().get(project_id)


def save_profile(project_id: str, **fields) -> dict:
    """Save or update project profile. Returns the full profile dict."""
    data = _load()
    existing = data.get(project_id, {})
    existing.update(fields)
    data[project_id] = existing
    _save(data)
    return existing


def list_projects() -> list[str]:
    """Return list of known project IDs."""
    return list(_load().keys())


def suggest_profile(project_id: str) -> dict | None:
    """Return profile if exists, with a 'last_run' hint for Agent to report."""
    p = get_profile(project_id)
    if p:
        p["_known"] = True
    return p
