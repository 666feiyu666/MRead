"""Acceptance 2, 3, 5, 7: a template run, a human pause, and a resumed run."""

from __future__ import annotations


def test_template_run_pauses_then_completes(client, case, workflow, fake):
    response = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    assert response.status_code == 200, response.text
    detail = response.json()

    assert detail["run"]["status"] == "awaiting_human"
    statuses = {record["step_name"]: record["status"] for record in detail["records"]}
    assert statuses == {
        "First reading": "completed",
        "Literature response": "completed",
        "Researcher question": "awaiting_human",
        "Revision in response": "pending",
    }
    assert detail["awaiting"]["step_id"] == "step3"

    first = next(record for record in detail["records"] if record["step_name"] == "First reading")
    assert first["output"]["note"]
    assert any(item["type"] == "observation" for item in first["output"]["evidence"])

    resumed = client.post(
        f"/api/runs/{detail['run']['id']}/decision",
        json={"step_id": "step3", "text": "Does the title date the scene, or only name it?"},
    )
    assert resumed.status_code == 200, resumed.text
    final = resumed.json()
    assert final["run"]["status"] == "completed"
    assert {record["status"] for record in final["records"]} == {"completed"}

    revision = next(record for record in final["records"] if record["step_name"] == "Revision in response")
    assert revision["payload"]["human_decision"]["text"].startswith("Does the title")
    assert final["decisions"][0]["step_id"] == "step3"


def test_repeated_decision_is_rejected(client, case, workflow, fake):
    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}).json()
    run_id = run["run"]["id"]
    first = client.post(f"/api/runs/{run_id}/decision", json={"step_id": "step3", "text": "one question"})
    assert first.status_code == 200
    again = client.post(f"/api/runs/{run_id}/decision", json={"step_id": "step3", "text": "second"})
    assert again.status_code == 409


def test_decision_for_the_wrong_step_is_rejected(client, case, workflow, fake):
    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}).json()
    run_id = run["run"]["id"]
    wrong = client.post(f"/api/runs/{run_id}/decision", json={"step_id": "step1", "text": "not the human step"})
    assert wrong.status_code == 409


def test_reload_restores_the_exchange(client, case, workflow, fake):
    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}).json()
    run_id = run["run"]["id"]
    client.post(f"/api/runs/{run_id}/decision", json={"step_id": "step3", "text": "keep the disagreement"})

    fetched = client.get(f"/api/runs/{run_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["run"]["status"] == "completed"
    assert len(body["records"]) == 4
    assert body["snapshot"]["workflow"]["version"] == workflow["version"]
    assert body["case"]["title"] == "Night Revels, a detail"


def test_earlier_output_is_not_overwritten_by_the_revision(client, case, workflow, fake):
    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}).json()
    run_id = run["run"]["id"]
    first_note = next(r for r in run["records"] if r["step_name"] == "First reading")["output"]["note"]
    client.post(f"/api/runs/{run_id}/decision", json={"step_id": "step3", "text": "reconsider"})

    body = client.get(f"/api/runs/{run_id}").json()
    records = body["records"]
    assert records[0]["output"]["note"] == first_note
    assert records[3]["output"]["note"] != first_note
    # The same profile served both steps, but created two distinct records.
    assert records[0]["payload"]["profile_id"] == records[3]["payload"]["profile_id"]
    assert records[0]["id"] != records[3]["id"]
