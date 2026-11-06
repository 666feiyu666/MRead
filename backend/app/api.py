"""HTTP surface.

Routes are named for what they do — cases, materials, profiles, workflows, runs,
decisions — never for an agent called A or B.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from . import assets as assets_mod
from . import config, engine, graph, store
from .db import session
from .schemas import (
    AgentProfileIn,
    CaseIn,
    DecisionIn,
    RunIn,
    WorkflowIn,
)

router = APIRouter(prefix="/api")


def _conn():
    return session()


# ------------------------------------------------------------------------ health


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "provider": config.PROVIDER}


@router.get("/config")
def read_config() -> dict[str, Any]:
    """What the UI may know about the model setup. Never includes the key itself."""
    return {
        "provider": config.PROVIDER,
        "default_model": config.DEFAULT_MODEL,
        "key_configured": bool(config.OPENAI_API_KEY),
        "base_url_host": _host_only(config.OPENAI_BASE_URL),
        "image_input": not config.TEXT_ONLY,
        "data_profile": config.DATA_PROFILE,
        "data_dir": str(config.DATA_DIR),
    }


def _host_only(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0]


# ------------------------------------------------------------------------- cases


@router.post("/cases")
def create_case(body: CaseIn) -> dict[str, Any]:
    with _conn() as conn:
        return store.create_case(conn, title=body.title, notes=body.notes)


@router.get("/cases")
def list_cases() -> list[dict[str, Any]]:
    with _conn() as conn:
        return store.list_cases(conn)


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    with _conn() as conn:
        case = store.get_case(conn, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="unknown case")
        case["assets"] = store.list_assets(conn, case_id)
        case["workflows"] = store.list_workflows(conn, case_id)
        case["runs"] = store.list_runs(conn, case_id)
        return case


# ----------------------------------------------------------------------- assets


@router.post("/cases/{case_id}/assets")
async def upload_asset(
    case_id: str,
    kind: str = Form(...),
    title: str = Form(""),
    provenance: str = Form(""),
    pasted_text: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    with _conn() as conn:
        if not store.get_case(conn, case_id):
            raise HTTPException(status_code=404, detail="unknown case")
        data = await file.read() if file is not None else b""
        try:
            stored = assets_mod.store_upload(
                kind=kind,
                filename=file.filename if file else "",
                mime=file.content_type if file else "",
                data=data,
                pasted_text=pasted_text,
            )
        except assets_mod.UploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = assets_mod.insert_asset(
            conn, case_id=case_id, asset=stored, title=title, provenance=provenance
        )
        asset = store.get_asset(conn, result["id"])
        return {key: value for key, value in asset.items() if key not in {"stored_path", "text_content"}}


@router.get("/cases/{case_id}/materials")
def list_case_materials(case_id: str) -> dict[str, Any]:
    """Every material of a case, with where it is bound and whether a run has used it."""
    with _conn() as conn:
        if not store.get_case(conn, case_id):
            raise HTTPException(status_code=404, detail="unknown case")
        assets = store.list_assets(conn, case_id)
        references = store.asset_references(conn, case_id)
    for asset in assets:
        asset["references"] = references.get(asset["id"], {"workflows": [], "runs": 0})
    return {"assets": assets}


class AssetPatchIn(BaseModel):
    title: str | None = None
    provenance: str | None = None


@router.patch("/assets/{asset_id}")
def patch_asset(asset_id: str, body: AssetPatchIn) -> dict[str, Any]:
    with _conn() as conn:
        asset = store.get_asset(conn, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="unknown material")
        title = body.title if body.title is not None else asset["title"]
        provenance = body.provenance if body.provenance is not None else asset["provenance"]
        conn.execute(
            "UPDATE assets SET title = ?, provenance = ? WHERE id = ?",
            (title, provenance, asset_id),
        )
        asset = store.get_asset(conn, asset_id)
        return {
            "id": asset["id"],
            "case_id": asset["case_id"],
            "kind": asset["kind"],
            "title": asset["title"],
            "provenance": asset["provenance"],
        }


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, Any]:
    """Delete a material, remove it from every workflow step, and drop its file."""
    with _conn() as conn:
        result = store.delete_asset(conn, asset_id)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown material")
    return result


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict[str, Any]:
    with _conn() as conn:
        asset = store.get_asset(conn, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="unknown material")
        return {
            "id": asset["id"],
            "case_id": asset["case_id"],
            "kind": asset["kind"],
            "title": asset["title"],
            "provenance": asset["provenance"],
            "mime": asset["mime"],
            "size": asset["size"],
            "text": asset["text_content"] if asset["kind"] != "image" else "",
            "created_at": asset["created_at"],
        }


@router.get("/assets/{asset_id}/content")
def get_asset_content(asset_id: str):
    with _conn() as conn:
        asset = store.get_asset(conn, asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="unknown material")
        path = asset["stored_path"]
        if asset["kind"] == "image":
            return FileResponse(path, media_type=asset["mime"])
        return PlainTextResponse(asset["text_content"], media_type="text/plain; charset=utf-8")


# --------------------------------------------------------------------- profiles


@router.get("/profiles")
def list_profiles() -> list[dict[str, Any]]:
    with _conn() as conn:
        return store.list_profiles(conn)


@router.post("/profiles")
def create_profile(body: AgentProfileIn) -> dict[str, Any]:
    with _conn() as conn:
        return store.create_profile(conn, body.model_dump())


@router.patch("/profiles/{profile_id}")
def update_profile(profile_id: str, body: AgentProfileIn) -> dict[str, Any]:
    with _conn() as conn:
        updated = store.update_profile(conn, profile_id, body.model_dump())
        if not updated:
            raise HTTPException(status_code=404, detail="unknown agent profile")
        return updated


@router.post("/profiles/seed")
def seed_profiles() -> list[dict[str, Any]]:
    """Create the editable starting profiles described in the design document."""
    with _conn() as conn:
        existing = store.list_profiles(conn)
        if existing:
            return existing
        created = []
        for template in graph.DEFAULT_PROFILES:
            created.append(
                store.create_profile(
                    conn,
                    {
                        "name": template["name"],
                        "role_instructions": template["role_instructions"],
                        "model": "",
                        "expected_response": template["expected_response"],
                    },
                )
            )
        return created


# -------------------------------------------------------------------- workflows


@router.get("/workflows")
def list_workflows(case_id: str | None = None) -> list[dict[str, Any]]:
    with _conn() as conn:
        return store.list_workflows(conn, case_id)


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    with _conn() as conn:
        workflow = store.get_workflow(conn, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="unknown workflow")
        return workflow


@router.post("/workflows")
def create_workflow(body: WorkflowIn) -> dict[str, Any]:
    with _conn() as conn:
        if not store.get_case(conn, body.case_id):
            raise HTTPException(status_code=404, detail="unknown case")
        try:
            _validate(conn, body)
        except graph.WorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return store.create_workflow(conn, case_id=body.case_id, definition=body.model_dump(mode="json"))


@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, body: WorkflowIn) -> dict[str, Any]:
    with _conn() as conn:
        existing = store.get_workflow(conn, workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail="unknown workflow")
        try:
            _validate(conn, body)
        except graph.WorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return store.update_workflow(conn, workflow_id, body.model_dump(mode="json"))


class TemplateIn(BaseModel):
    case_id: str
    profile_ids: list[str] = []
    material_ids: list[str] = []


@router.post("/workflows/template")
def create_template(body: TemplateIn) -> dict[str, Any]:
    """Create the editable image → literature → researcher → return starting point."""
    with _conn() as conn:
        if not store.get_case(conn, body.case_id):
            raise HTTPException(status_code=404, detail="unknown case")
        profiles = body.profile_ids or [profile["id"] for profile in store.list_profiles(conn)]
        kinds = store.case_asset_kinds(conn, body.case_id)
        if body.material_ids:
            materials = [{"id": mid, "kind": kinds.get(mid, "")} for mid in body.material_ids]
        else:
            materials = [{"id": mid, "kind": kind} for mid, kind in sorted(kinds.items())]
        definition = graph.default_template(body.case_id, materials, profiles)
        try:
            _validate(conn, WorkflowIn.model_validate(definition))
        except graph.WorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return store.create_workflow(conn, case_id=body.case_id, definition=definition)


class PreviewIn(BaseModel):
    case_id: str
    workflow: WorkflowIn


@router.post("/workflows/preview")
def preview_workflow(body: PreviewIn) -> dict[str, Any]:
    """Show exactly what each step would be given, before anything is run."""
    with _conn() as conn:
        try:
            plan = _validate(conn, body.workflow)
        except graph.WorkflowError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        kinds = store.case_asset_kinds(conn, body.case_id)
        return {
            "steps": [
                {
                    "step_id": item.step["id"],
                    "step_name": item.step["name"],
                    "kind": item.step["kind"],
                    "profile_id": item.step.get("profile_id"),
                    "material_ids": item.step.get("material_ids", []),
                    "materials": [
                        {"asset_id": mid, "kind": kinds.get(mid)}
                        for mid in item.step.get("material_ids", [])
                    ],
                    "prior_step_ids": item.upstream,
                }
                for item in plan.steps
            ]
        }


def _validate(conn, workflow: WorkflowIn):
    return graph.validate_workflow(
        workflow,
        material_ids=store.case_material_ids(conn, workflow.case_id),
        profile_ids=store.profile_ids(conn),
        asset_kinds=store.case_asset_kinds(conn, workflow.case_id),
    )


# ------------------------------------------------------------------------- runs


@router.post("/runs")
def create_run(body: RunIn) -> dict[str, Any]:
    with _conn() as conn:
        try:
            run = engine.plan_run(
                conn,
                case_id=body.case_id,
                workflow_id=body.workflow_id,
                provider_name=config.PROVIDER,
            )
        except (engine.RunError, graph.WorkflowError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    _kick(run["id"])
    with _conn() as conn:
        return _run_detail(conn, run["id"])


@router.get("/runs")
def list_runs(case_id: str | None = None) -> list[dict[str, Any]]:
    with _conn() as conn:
        return store.list_runs(conn, case_id)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    with _conn() as conn:
        return _run_detail(conn, run_id)


@router.post("/runs/{run_id}/decision")
def submit_decision(run_id: str, body: DecisionIn) -> dict[str, Any]:
    with _conn() as conn:
        run = store.get_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="unknown run")
        if run["status"] != "awaiting_human":
            raise HTTPException(status_code=409, detail="this run is not waiting for a decision")
        record = store.record_for_step(conn, run_id, body.step_id)
        if not record or record["status"] != "awaiting_human":
            raise HTTPException(status_code=409, detail="this step is not the one waiting")
        if store.get_decision(conn, run_id, body.step_id):
            raise HTTPException(status_code=409, detail="a decision was already recorded for this step")
        store.insert_decision(conn, run_id=run_id, step_id=body.step_id, text=body.text)
        store.set_run_status(conn, run_id, "running")
    _kick(run_id)
    with _conn() as conn:
        return _run_detail(conn, run_id)


def _kick(run_id: str) -> None:
    if config.SYNC_RUNS:
        engine.advance_sync(run_id)
    else:
        engine.start(run_id)


def _run_detail(conn, run_id: str) -> dict[str, Any]:
    run = store.get_run(conn, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="unknown run")
    records = store.list_records(conn, run_id)
    decisions = store.list_decisions(conn, run_id)
    awaiting = next((record for record in records if record["status"] == "awaiting_human"), None)
    case = store.get_case(conn, run["case_id"])
    return {
        "run": {
            "id": run["id"],
            "case_id": run["case_id"],
            "workflow_id": run["workflow_id"],
            "workflow_version": run["workflow_version"],
            "status": run["status"],
            "provider": run["provider"],
            "error": run["error"],
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
        },
        "snapshot": run["snapshot"],
        "records": records,
        "decisions": decisions,
        "awaiting": (
            {
                "step_id": awaiting["step_id"],
                "step_name": awaiting["step_name"],
                "human_prompt": (awaiting["payload"] or {}).get("human_prompt", ""),
            }
            if awaiting
            else None
        ),
        "case": case,
    }
