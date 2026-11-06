"""Deterministic step scheduler.

The scheduler walks a workflow's topological order once. For each agent step it
assembles a payload from the step's explicit material bindings plus the outputs its
incoming edges hand over, makes one model call, validates the response, and stores a
record. A human step stops the run until the researcher submits one decision.

Nothing here keys off a step's or profile's name.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from . import assets as assets_mod
from . import config, store, validate
from .provider import ImagePart, ModelRequest, Provider, ProviderError, build_provider
from .schemas import new_id, utcnow

_registry: dict[str, Provider] = {}
_registry_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class RunError(RuntimeError):
    """A run cannot proceed. The message is safe to show to the researcher."""


def register_provider(name: str, provider: Provider) -> None:
    with _registry_lock:
        _registry[name] = provider


def provider_for(name: str) -> Provider:
    with _registry_lock:
        existing = _registry.get(name)
    if existing is not None:
        return existing
    provider = build_provider(name)
    register_provider(name, provider)
    return provider


def _lock_for(run_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _run_locks.get(run_id)
        if lock is None:
            lock = threading.Lock()
            _run_locks[run_id] = lock
        return lock


# ------------------------------------------------------------------ run creation


def plan_run(conn, *, case_id: str, workflow_id: str, provider_name: str) -> dict[str, Any]:
    """Snapshot everything a run depends on, then create its pending step records."""
    from .graph import Plan, PlannedStep, validate_workflow
    from .schemas import WorkflowIn

    case = store.get_case(conn, case_id)
    if not case:
        raise RunError("unknown case")
    workflow = store.get_workflow(conn, workflow_id)
    if not workflow:
        raise RunError("unknown workflow")
    if workflow["case_id"] != case_id:
        raise RunError("this workflow belongs to a different case")

    definition = workflow["definition"]
    material_ids = store.case_material_ids(conn, case_id)
    kinds = store.case_asset_kinds(conn, case_id)
    known_profiles = store.profile_ids(conn)

    plan = validate_workflow(
        WorkflowIn.model_validate(definition),
        material_ids=material_ids,
        profile_ids=known_profiles,
        asset_kinds=kinds,
    )

    profiles: dict[str, Any] = {}
    for planned in plan.steps:
        profile_id = planned.step.get("profile_id")
        if profile_id and profile_id not in profiles:
            profile = store.get_profile(conn, profile_id)
            if not profile:
                raise RunError(f"unknown agent profile {profile_id}")
            profiles[profile_id] = profile

    snapshot = {
        "case": {"id": case["id"], "title": case["title"]},
        "workflow": {"id": workflow["id"], "name": workflow["name"], "version": workflow["version"]},
        "definition": definition,
        "plan": [
            {
                "step": item.step,
                "ordinal": item.ordinal,
                "upstream": item.upstream,
            }
            for item in plan.steps
        ],
        "profiles": profiles,
        "material_ids": sorted(material_ids),
    }

    run = store.create_run(
        conn,
        case_id=case_id,
        workflow_id=workflow_id,
        workflow_version=workflow["version"],
        provider=provider_name,
        snapshot=snapshot,
    )
    for planned in plan.steps:
        store.insert_record(
            conn,
            run_id=run["id"],
            step_id=planned.step["id"],
            step_name=planned.step["name"],
            kind=planned.step["kind"],
            ordinal=planned.ordinal,
            status="pending",
        )
    return store.get_run(conn, run["id"])


def start(run_id: str) -> None:
    """Run in a background thread so the HTTP request can return immediately."""
    thread = threading.Thread(target=_advance_guarded, args=(run_id,), daemon=True)
    thread.start()


def _advance_guarded(run_id: str) -> None:
    lock = _lock_for(run_id)
    if not lock.acquire(blocking=False):
        return
    conn = None
    try:
        from .db import connect

        conn = connect()
        _advance(conn, run_id)
    except Exception:  # noqa: BLE001 - a crashing run must end as a failed run
        try:
            if conn is not None:
                store.set_run_status(conn, run_id, "failed", "the run stopped unexpectedly")
        except Exception:  # noqa: BLE001
            pass
    finally:
        if conn is not None:
            conn.close()
        lock.release()


def advance_sync(run_id: str) -> None:
    """Synchronous advance, used by tests and by the decision endpoint."""
    _advance_guarded(run_id)


# ----------------------------------------------------------------------- engine


def _advance(conn, run_id: str) -> None:
    run = store.get_run(conn, run_id)
    if not run:
        raise RunError("unknown run")
    if run["status"] in {"completed", "failed"}:
        return
    if run["status"] not in {"queued", "running", "awaiting_human"}:
        return

    store.set_run_status(conn, run_id, "running")
    plan = run["snapshot"]["plan"]

    while True:
        records = store.list_records(conn, run_id)
        records_by_step = {record["step_id"]: record for record in records}
        current = next((record for record in records if record["status"] in {"pending", "awaiting_human"}), None)
        if current is None:
            store.set_run_status(conn, run_id, "completed")
            return

        planned = next(item for item in plan if item["step"]["id"] == current["step_id"])
        step = planned["step"]

        if step["kind"] == "human":
            decision = store.get_decision(conn, run_id, step["id"])
            if decision is None:
                store.update_record(
                    conn,
                    current["id"],
                    status="awaiting_human",
                    payload={
                        "step_id": step["id"],
                        "step_name": step["name"],
                        "kind": "human",
                        "human_prompt": step.get("human_prompt", ""),
                        "prior_step_ids": [item["step_id"] for item in _upstream_records(records_by_step, planned)],
                    },
                )
                store.set_run_status(conn, run_id, "awaiting_human")
                return
            store.update_record(
                conn,
                current["id"],
                status="completed",
                started_at=current["started_at"] or utcnow(),
                finished_at=utcnow(),
                output={"note": decision["text"], "evidence": [], "unresolved": [], "decision_id": decision["id"]},
            )
            continue

        ok = _run_agent_step(conn, run, planned, current, records_by_step)
        if not ok:
            return


def _upstream_records(records_by_step: dict[str, dict], planned: dict[str, Any]) -> list[dict[str, Any]]:
    return [records_by_step[sid] for sid in planned["upstream"] if sid in records_by_step]


def _run_agent_step(conn, run, planned, record, records_by_step) -> bool:
    step = planned["step"]
    profile = run["snapshot"]["profiles"].get(step.get("profile_id")) or {}
    model = (profile.get("model") or "").strip() or config.DEFAULT_MODEL

    materials = []
    for material_id in step.get("material_ids", []):
        asset = store.get_asset(conn, material_id)
        if not asset or asset["case_id"] != run["case_id"]:
            store.update_record(conn, record["id"], status="failed", error="a bound material is missing")
            store.set_run_status(conn, run["id"], "failed", "a bound material is missing")
            return False
        materials.append(asset)

    upstream = _upstream_records(records_by_step, planned)
    decisions = {decision["step_id"]: decision for decision in store.list_decisions(conn, run["id"])}

    payload = {
        "step_id": step["id"],
        "step_name": step["name"],
        "kind": "agent",
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "model": model,
        "material_ids": [asset["id"] for asset in materials],
        "prior_step_ids": [item["step_id"] for item in upstream],
        "materials": [
            {
                "asset_id": asset["id"],
                "kind": asset["kind"],
                "title": asset["title"],
                "provenance": asset["provenance"],
                "text_chars": len(asset["text_content"] or ""),
                "image_included": asset["kind"] == "image",
                "text_included": asset["kind"] in {"article", "note"},
            }
            for asset in materials
        ],
        "human_decision": None,
    }
    for upstream_record in upstream:
        if upstream_record["kind"] == "human":
            decision = decisions.get(upstream_record["step_id"])
            if decision:
                payload["human_decision"] = {"step_id": decision["step_id"], "text": decision["text"]}

    store.update_record(
        conn,
        record["id"],
        status="running",
        payload=payload,
        started_at=utcnow(),
        error="",
    )

    user_text = _compose_user_text(run, step, materials, upstream, payload["human_decision"])
    images: list[ImagePart] = []
    if not config.TEXT_ONLY:
        for asset in materials:
            if asset["kind"] != "image":
                continue
            try:
                images.append(
                    ImagePart(
                        asset_id=asset["id"],
                        data=assets_mod.asset_bytes(asset["stored_path"]),
                        mime=asset["mime"],
                    )
                )
            except assets_mod.UploadError as exc:
                store.update_record(conn, record["id"], status="failed", error=str(exc))
                store.set_run_status(conn, run["id"], "failed", str(exc))
                return False
    payload["image_parts_sent"] = len(images)
    store.update_record(conn, record["id"], payload=payload)

    system = _compose_system(profile)
    request = ModelRequest(model=model, system=system, user_text=user_text, images=images)

    try:
        provider = provider_for(run["provider"])
        raw = provider.complete(request)
    except ProviderError as exc:
        store.update_record(conn, record["id"], status="failed", error=str(exc), finished_at=utcnow())
        store.set_run_status(conn, run["id"], "failed", str(exc))
        return False

    allowed = {asset["id"]: asset for asset in materials}
    text_lengths = {
        asset["id"]: len(asset["text_content"] or "")
        for asset in materials
        if asset["kind"] in {"article", "note"}
    }
    prior_index = store.evidence_index(conn, run["id"])
    referenced_assets = {
        entry["item"].get("asset_id")
        for entry in prior_index.values()
        if entry["kind"] == "evidence" and entry["item"].get("asset_id")
    }

    try:
        output = validate.parse_output(
            raw,
            allowed_assets=allowed,
            asset_text_lengths=text_lengths,
            referenced_assets={item for item in referenced_assets if item},
            prior_index=prior_index,
        )
    except validate.OutputError as exc:
        store.update_record(
            conn,
            record["id"],
            status="failed",
            error=str(exc),
            raw_output=raw[:20000],
            finished_at=utcnow(),
        )
        store.set_run_status(conn, run["id"], "failed", str(exc))
        return False

    store.update_record(
        conn,
        record["id"],
        status="completed",
        output=output,
        raw_output=raw[:20000],
        finished_at=utcnow(),
    )
    store.set_run_status(conn, run["id"], "running")
    return True


def _compose_system(profile: dict[str, Any]) -> str:
    parts = [
        "You are one step of a reading workflow that helps a researcher read images critically.",
        "You see only the materials listed in this message. Nothing else is available to you.",
    ]
    if profile.get("role_instructions"):
        parts.append("YOUR ROLE\n" + profile["role_instructions"].strip())
    if profile.get("expected_response"):
        parts.append("EXPECTED RESPONSE\n" + profile["expected_response"].strip())
    parts.append(validate.OUTPUT_CONTRACT)
    return "\n\n".join(parts)


def _compose_user_text(run, step, materials, upstream, human_decision) -> str:
    lines: list[str] = []
    case = run["snapshot"]["case"]
    lines.append(f"CASE: {case['title']}")
    lines.append(f"STEP: {step['name']}")
    lines.append("")
    lines.append("MATERIALS YOU MAY USE (only these):")
    if not materials:
        lines.append("(none — this step was given no material)")
    for asset in materials:
        lines.append(
            f"MATERIAL asset_id={asset['id']} kind={asset['kind']} "
            f"title={json.dumps(asset['title'], ensure_ascii=False)} "
            f"provenance={json.dumps(asset['provenance'], ensure_ascii=False)}"
        )
        if asset["kind"] in {"article", "note"}:
            text = asset["text_content"] or ""
            lines.append(f"--- text of {asset['id']} (characters 0..{len(text)}) ---")
            lines.append(text)
            lines.append(f"--- end of {asset['id']} ---")
        else:
            lines.append(f"--- image {asset['id']} is attached; describe only what is inside the frame ---")
    lines.append("")

    lines.append("EARLIER STEPS HANDED TO YOU:")
    if not upstream:
        lines.append("(none)")
    for record in upstream:
        output = record.get("output") or {}
        lines.append(f"[record {record['id']}] step {record['step_name']!r}:")
        lines.append(f"note: {output.get('note', '')}")
        for item in output.get("evidence", []):
            spot = []
            if item.get("region"):
                region = item["region"]
                spot.append(
                    f"region x={region['x']} y={region['y']} w={region['width']} h={region['height']}"
                )
            if item.get("passage"):
                spot.append(f"characters {item['passage']['start']}..{item['passage']['end']}")
            if item.get("asset_id"):
                spot.append(f"asset {item['asset_id']}")
            suffix = f" [{', '.join(spot)}]" if spot else ""
            lines.append(f"- {item['id']} ({item['type']}): {item['text']}{suffix}")
        for line in output.get("unresolved", []):
            lines.append(f"- unresolved: {line}")
        lines.append("")

    if human_decision:
        lines.append(f"RESEARCHER DECISION (from human step {human_decision['step_id']}):")
        lines.append(human_decision["text"])
        lines.append("")

    lines.append(
        "Answer only from the materials above. If something cannot be settled from them, "
        'put it under "unresolved" instead of concluding.'
    )
    return "\n".join(lines)
