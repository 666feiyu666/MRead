"""CRUD helpers over the SQLite schema. No business rules live here."""

from __future__ import annotations

import json
from typing import Any

from .db import loads, row_to_dict
from .schemas import new_id, utcnow

RECORD_JSON = ("payload", "output")


# ------------------------------------------------------------------------ cases


def create_case(conn, *, title: str, notes: str = "") -> dict[str, Any]:
    case_id = new_id("case")
    conn.execute(
        "INSERT INTO cases (id, title, notes, created_at) VALUES (?, ?, ?, ?)",
        (case_id, title, notes, utcnow()),
    )
    return get_case(conn, case_id)


def get_case(conn, case_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_cases(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [row_to_dict(row) for row in rows]


# ----------------------------------------------------------------------- assets

ASSET_PUBLIC = (
    "id, case_id, kind, title, provenance, filename, mime, size, created_at"
)


def get_asset(conn, asset_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_assets(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"SELECT {ASSET_PUBLIC} FROM assets WHERE case_id = ? ORDER BY created_at",
        (case_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def case_material_ids(conn, case_id: str) -> set[str]:
    rows = conn.execute("SELECT id FROM assets WHERE case_id = ?", (case_id,)).fetchall()
    return {row["id"] for row in rows}


def case_asset_kinds(conn, case_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT id, kind FROM assets WHERE case_id = ?", (case_id,)).fetchall()
    return {row["id"]: row["kind"] for row in rows}


# --------------------------------------------------------------------- profiles


def create_profile(conn, data: dict[str, Any]) -> dict[str, Any]:
    profile_id = new_id("prof")
    now = utcnow()
    conn.execute(
        """INSERT INTO profiles (id, name, role_instructions, model, expected_response,
                                 version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            profile_id,
            data["name"],
            data["role_instructions"],
            data.get("model", ""),
            data.get("expected_response", ""),
            now,
            now,
        ),
    )
    return get_profile(conn, profile_id)


def update_profile(conn, profile_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    current = get_profile(conn, profile_id)
    if not current:
        return None
    conn.execute(
        """UPDATE profiles SET name = ?, role_instructions = ?, model = ?,
                               expected_response = ?, version = version + 1, updated_at = ?
           WHERE id = ?""",
        (
            data.get("name", current["name"]),
            data.get("role_instructions", current["role_instructions"]),
            data.get("model", current["model"]),
            data.get("expected_response", current["expected_response"]),
            utcnow(),
            profile_id,
        ),
    )
    return get_profile(conn, profile_id)


def get_profile(conn, profile_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_profiles(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
    return [row_to_dict(row) for row in rows]


def profile_ids(conn) -> set[str]:
    return {row["id"] for row in conn.execute("SELECT id FROM profiles")}


# -------------------------------------------------------------------- workflows


def create_workflow(conn, *, case_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    workflow_id = new_id("wf")
    now = utcnow()
    conn.execute(
        """INSERT INTO workflows (id, case_id, name, version, definition, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?, ?)""",
        (workflow_id, case_id, definition["name"], json.dumps(definition), now, now),
    )
    return get_workflow(conn, workflow_id)


def update_workflow(conn, workflow_id: str, definition: dict[str, Any]) -> dict[str, Any] | None:
    current = get_workflow(conn, workflow_id)
    if not current:
        return None
    conn.execute(
        """UPDATE workflows SET name = ?, definition = ?, version = version + 1, updated_at = ?
           WHERE id = ?""",
        (definition["name"], json.dumps(definition), utcnow(), workflow_id),
    )
    return get_workflow(conn, workflow_id)


def get_workflow(conn, workflow_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
    if not row:
        return None
    return row_to_dict(row, ("definition",))


def list_workflows(conn, case_id: str | None = None) -> list[dict[str, Any]]:
    if case_id:
        rows = conn.execute(
            "SELECT * FROM workflows WHERE case_id = ? ORDER BY created_at", (case_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at").fetchall()
    return [row_to_dict(row, ("definition",)) for row in rows]


# ------------------------------------------------------------------------- runs


def create_run(
    conn,
    *,
    case_id: str,
    workflow_id: str,
    workflow_version: int,
    provider: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    run_id = new_id("run")
    now = utcnow()
    conn.execute(
        """INSERT INTO runs (id, case_id, workflow_id, workflow_version, status, provider,
                             snapshot, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
        (run_id, case_id, workflow_id, workflow_version, provider, json.dumps(snapshot), now, now),
    )
    return get_run(conn, run_id)


def get_run(conn, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row_to_dict(row, ("snapshot",)) if row else None


def list_runs(conn, case_id: str | None = None) -> list[dict[str, Any]]:
    if case_id:
        rows = conn.execute(
            "SELECT * FROM runs WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    return [row_to_dict(row) for row in rows]


def set_run_status(conn, run_id: str, status: str, error: str = "") -> None:
    conn.execute(
        "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, error, utcnow(), run_id),
    )


# ----------------------------------------------------------------- step records


def insert_record(
    conn,
    *,
    run_id: str,
    step_id: str,
    step_name: str,
    kind: str,
    ordinal: int,
    status: str = "pending",
) -> dict[str, Any]:
    record_id = new_id("rec")
    conn.execute(
        """INSERT INTO step_records (id, run_id, step_id, step_name, kind, ordinal, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (record_id, run_id, step_id, step_name, kind, ordinal, status),
    )
    return get_record(conn, record_id)


def get_record(conn, record_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM step_records WHERE id = ?", (record_id,)).fetchone()
    return row_to_dict(row, RECORD_JSON) if row else None


def list_records(conn, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM step_records WHERE run_id = ? ORDER BY ordinal", (run_id,)
    ).fetchall()
    return [row_to_dict(row, RECORD_JSON) for row in rows]


def record_for_step(conn, run_id: str, step_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM step_records WHERE run_id = ? AND step_id = ?", (run_id, step_id)
    ).fetchone()
    return row_to_dict(row, RECORD_JSON) if row else None


def update_record(conn, record_id: str, **fields: Any) -> None:
    allowed = {"status", "payload", "output", "raw_output", "error", "started_at", "finished_at"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    for key in ("payload", "output"):
        if key in updates and not isinstance(updates[key], str):
            updates[key] = json.dumps(updates[key])
    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE step_records SET {assignments} WHERE id = ?",
        (*updates.values(), record_id),
    )


# --------------------------------------------------------------------- decisions


def insert_decision(conn, *, run_id: str, step_id: str, text: str) -> dict[str, Any]:
    decision_id = new_id("dec")
    conn.execute(
        "INSERT INTO decisions (id, run_id, step_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (decision_id, run_id, step_id, text, utcnow()),
    )
    return get_decision(conn, run_id, step_id)


def get_decision(conn, run_id: str, step_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM decisions WHERE run_id = ? AND step_id = ?", (run_id, step_id)
    ).fetchone()
    return row_to_dict(row) if row else None


def list_decisions(conn, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM decisions WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def evidence_index(conn, run_id: str) -> dict[str, dict[str, Any]]:
    """Every evidence item and record already produced in this run, by id."""
    index: dict[str, dict[str, Any]] = {}
    for record in list_records(conn, run_id):
        if record["status"] != "completed":
            continue
        index[record["id"]] = {"kind": "record", "record": record}
        for item in record["output"].get("evidence", []):
            if isinstance(item, dict) and item.get("id"):
                index[item["id"]] = {"kind": "evidence", "record_id": record["id"], "item": item}
    return index


def loads_json(value: str, default):
    return loads(value, default)
