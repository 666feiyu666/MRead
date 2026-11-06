"""CRUD helpers over the SQLite schema. No business rules live here."""

from __future__ import annotations

import json
from pathlib import Path
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
    "id, case_id, kind, title, provenance, filename, mime, size, created_at, "
    "length(text_content) AS text_chars"
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


def list_run_summaries(
    conn, case_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """One row per run, with just enough to recognise it in a history list."""
    sql = "SELECT * FROM runs"
    params: tuple[Any, ...] = ()
    if case_id:
        sql += " WHERE case_id = ?"
        params = (case_id,)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    rows = conn.execute(sql, (*params, limit)).fetchall()
    if not rows:
        return []

    run_ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in run_ids)
    records = conn.execute(
        f"""SELECT run_id, step_id, kind, status, ordinal, output
            FROM step_records WHERE run_id IN ({placeholders}) ORDER BY ordinal""",
        run_ids,
    ).fetchall()

    by_run: dict[str, list[Any]] = {}
    for record in records:
        by_run.setdefault(record["run_id"], []).append(record)

    summaries: list[dict[str, Any]] = []
    for row in rows:
        steps = by_run.get(row["id"], [])
        first_note = ""
        for record in steps:
            if record["status"] != "completed" or record["kind"] != "agent":
                continue
            output = loads(record["output"], {})
            note = output.get("note", "") if isinstance(output, dict) else ""
            if note:
                first_note = str(note).strip()
                break
        summaries.append(
            {
                "id": row["id"],
                "case_id": row["case_id"],
                "workflow_id": row["workflow_id"],
                "workflow_version": row["workflow_version"],
                "status": row["status"],
                "provider": row["provider"],
                "error": row["error"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "step_count": len(steps),
                "completed_steps": sum(1 for record in steps if record["status"] == "completed"),
                "awaiting_step_id": next(
                    (record["step_id"] for record in steps if record["status"] == "awaiting_human"),
                    None,
                ),
                "first_note": first_note[:160],
            }
        )
    return summaries


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


# --------------------------------------------------------------- material upkeep


def asset_references(conn, case_id: str) -> dict[str, dict[str, Any]]:
    """Where each material of a case is used: workflow step bindings and run usage."""
    references: dict[str, dict[str, Any]] = {
        asset_id: {"workflows": [], "runs": 0} for asset_id in case_material_ids(conn, case_id)
    }

    for workflow in list_workflows(conn, case_id):
        for step in workflow["definition"].get("steps", []):
            for material_id in step.get("material_ids", []):
                entry = references.setdefault(material_id, {"workflows": [], "runs": 0})
                entry["workflows"].append(
                    {
                        "workflow_id": workflow["id"],
                        "workflow_name": workflow["name"],
                        "workflow_version": workflow["version"],
                        "step_id": step.get("id"),
                        "step_name": step.get("name"),
                    }
                )

    rows = conn.execute(
        """SELECT record.run_id AS run_id, record.payload AS payload
           FROM step_records AS record
           JOIN runs AS run ON run.id = record.run_id
           WHERE run.case_id = ?""",
        (case_id,),
    ).fetchall()
    seen_runs: dict[str, set[str]] = {}
    for row in rows:
        payload = loads(row["payload"], {})
        if not isinstance(payload, dict):
            continue
        for material_id in payload.get("material_ids", []):
            seen_runs.setdefault(material_id, set()).add(row["run_id"])
    for material_id, run_ids in seen_runs.items():
        if material_id in references:
            references[material_id]["runs"] = len(run_ids)
    return references


def unbind_asset(conn, asset_id: str) -> list[dict[str, Any]]:
    """Remove a material from every workflow step that binds it. Bumps each version."""
    changed: list[dict[str, Any]] = []
    rows = conn.execute("SELECT id, case_id, name, version, definition FROM workflows").fetchall()
    for row in rows:
        definition = loads(row["definition"], {})
        touched = False
        for step in definition.get("steps", []):
            material_ids = step.get("material_ids", [])
            if asset_id in material_ids:
                step["material_ids"] = [mid for mid in material_ids if mid != asset_id]
                touched = True
                changed.append(
                    {
                        "workflow_id": row["id"],
                        "workflow_name": row["name"],
                        "step_id": step.get("id"),
                        "step_name": step.get("name"),
                    }
                )
        if touched:
            conn.execute(
                """UPDATE workflows SET definition = ?, version = version + 1, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(definition), utcnow(), row["id"]),
            )
    return changed


def delete_asset(conn, asset_id: str) -> dict[str, Any] | None:
    """Delete a material row, its file when no other row shares it, and its bindings."""
    asset = get_asset(conn, asset_id)
    if not asset:
        return None
    unbound = unbind_asset(conn, asset_id)
    shared = conn.execute(
        "SELECT count(*) FROM assets WHERE stored_path = ? AND id != ?",
        (asset["stored_path"], asset_id),
    ).fetchone()[0]
    conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    file_removed = False
    if not shared and asset["stored_path"]:
        path = Path(asset["stored_path"])
        try:
            if path.is_file():
                path.unlink()
                file_removed = True
        except OSError:
            file_removed = False
    return {"deleted": asset_id, "unbound_from": unbound, "file_removed": file_removed}
