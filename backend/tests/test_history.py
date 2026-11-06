"""Reading history: every run is kept, listed newest first, and stays readable."""

from __future__ import annotations


def _start(client, case, workflow):
    response = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_history_lists_every_run_newest_first(client, case, workflow, fake):
    first = _start(client, case, workflow)
    client.post(
        f"/api/runs/{first['run']['id']}/decision",
        json={"step_id": "step3", "text": "Which claim is weakest?"},
    )
    second = _start(client, case, workflow)

    rows = client.get(f"/api/runs?case_id={case['id']}").json()
    assert [row["id"] for row in rows] == [second["run"]["id"], first["run"]["id"]]

    newest, older = rows
    assert newest["step_count"] == 4
    assert newest["completed_steps"] == 2
    assert newest["awaiting_step_id"] == "step3"
    assert newest["first_note"].startswith("Fake reading for First reading")

    assert older["status"] == "completed"
    assert older["awaiting_step_id"] is None
    assert older["completed_steps"] == 4
    assert older["workflow_version"] == workflow["version"]


def test_history_keeps_the_snapshot_a_run_used(client, case, workflow, materials, fake):
    run = _start(client, case, workflow)
    client.post(f"/api/runs/{run['run']['id']}/decision", json={"step_id": "step3", "text": "q"})

    definition = workflow["definition"]
    definition["steps"] = definition["steps"][:2]
    definition["edges"] = definition["edges"][:1]
    client.put(f"/api/workflows/{workflow['id']}", json=definition)

    reloaded = client.get(f"/api/runs/{run['run']['id']}").json()
    assert len(reloaded["snapshot"]["definition"]["steps"]) == 4, "history keeps its own copy"
    rows = client.get(f"/api/runs?case_id={case['id']}").json()
    assert rows[0]["workflow_version"] == workflow["version"]


def test_history_limit_and_isolation_between_cases(client, case, workflow, fake):
    other = client.post("/api/cases", json={"title": "another case"}).json()
    for _ in range(3):
        _start(client, case, workflow)

    limited = client.get(f"/api/runs?case_id={case['id']}&limit=2").json()
    assert len(limited) == 2

    assert client.get(f"/api/runs?case_id={other['id']}").json() == []


def test_history_survives_a_deleted_material(client, case, workflow, materials, fake):
    run = _start(client, case, workflow)
    client.delete(f"/api/assets/{materials['article']['id']}")

    rows = client.get(f"/api/runs?case_id={case['id']}").json()
    assert [row["id"] for row in rows] == [run["run"]["id"]]
    records = client.get(f"/api/runs/{run['run']['id']}").json()["records"]
    assert len(records) == 4, "the reading itself is untouched"
