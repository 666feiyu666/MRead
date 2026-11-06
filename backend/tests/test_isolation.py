"""Acceptance 2 and 4: hidden material stays out of a call, and the record says so."""

from __future__ import annotations

from app import store
from app.db import session
from app.schemas import AgentProfileIn, WorkflowIn


def _run(client, case, workflow):
    response = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def _save_workflow(workflow, definition):
    with session() as conn:
        store.update_workflow(
            conn, workflow["id"], WorkflowIn.model_validate(definition).model_dump(mode="json")
        )


def test_first_reading_never_receives_the_article(client, case, workflow, materials, fake):
    _run(client, case, workflow)
    first_call = fake.calls[0]

    assert materials["article"]["id"] not in first_call["user_text"]
    assert "Later colophons" not in first_call["user_text"]
    assert "A note on the handscroll" not in first_call["user_text"]
    assert first_call["image_asset_ids"] == [materials["image"]["id"]]


def test_literature_step_receives_the_article_and_no_image(client, case, workflow, materials, fake):
    _run(client, case, workflow)
    second_call = fake.calls[1]

    assert materials["image"]["id"] in second_call["user_text"]
    assert "Later colophons" in second_call["user_text"]
    assert second_call["image_asset_ids"] == []
    assert "First reading" in second_call["user_text"]


def test_record_lists_exact_materials_and_prior_steps(client, case, workflow, materials, fake):
    detail = _run(client, case, workflow)
    records = {record["step_name"]: record for record in detail["records"]}

    assert records["First reading"]["payload"]["material_ids"] == [materials["image"]["id"]]
    assert records["First reading"]["payload"]["prior_step_ids"] == []

    assert records["Literature response"]["payload"]["material_ids"] == [materials["article"]["id"]]
    assert records["Literature response"]["payload"]["prior_step_ids"] == ["step1"]


def test_a_step_with_no_material_is_refused_before_running(client, case, workflow, materials, fake):
    """An agent step with nothing bound never reaches the model."""
    definition = workflow["definition"]
    definition["steps"][0]["material_ids"] = []
    _save_workflow(workflow, definition)

    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    assert run.status_code == 400, run.text
    assert "no material bound" in run.json()["detail"]
    assert "First reading" in run.json()["detail"]
    assert fake.calls == [], "no model call may be spent on an empty step"


def test_giving_the_literature_agent_the_image_changes_its_call(client, case, workflow, materials, fake):
    """A label never grants access; an explicit binding does."""
    definition = workflow["definition"]
    definition["steps"][1]["material_ids"] = [materials["image"]["id"]]
    _save_workflow(workflow, definition)

    _run(client, case, workflow)
    second_call = fake.calls[1]
    assert second_call["image_asset_ids"] == [materials["image"]["id"]]
    assert "Later colophons" not in second_call["user_text"]


def test_profile_instructions_change_the_request(client, case, workflow, profiles, fake):
    reader = next(profile for profile in profiles if profile["name"] == "Image reader")
    updated = client.patch(
        f"/api/profiles/{reader['id']}",
        json={
            "name": reader["name"],
            "role_instructions": "Read only the furniture. Do not describe faces at all.",
            "model": "deepseek-chat",
            "expected_response": "A list of objects.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == reader["version"] + 1

    _run(client, case, workflow)
    assert "Read only the furniture." in fake.calls[0]["system"]
    assert "A list of objects." in fake.calls[0]["system"]
    assert "Read only the furniture." not in fake.calls[1]["system"]


def test_a_run_keeps_the_profile_it_started_with(client, case, workflow, profiles, fake):
    run = _run(client, case, workflow)
    reader = next(profile for profile in profiles if profile["name"] == "Image reader")
    before = run["snapshot"]["profiles"][reader["id"]]["role_instructions"]

    client.patch(
        f"/api/profiles/{reader['id']}",
        json={
            "name": reader["name"],
            "role_instructions": "A completely different instruction.",
            "model": "",
            "expected_response": "",
        },
    )
    reloaded = client.get(f"/api/runs/{run['run']['id']}").json()
    assert reloaded["snapshot"]["profiles"][reader["id"]]["role_instructions"] == before
    assert "completely different" not in fake.calls[0]["system"]
