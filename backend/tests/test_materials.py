"""Material management: what is bound to what, renaming, and deletion that unbinds."""

from __future__ import annotations

from pathlib import Path

from app import store
from app.db import session
from tests.conftest import ARTICLE_TEXT, PNG_1PX


def _stored_path(asset_id: str) -> str:
    with session() as conn:
        return store.get_asset(conn, asset_id)["stored_path"]


def test_materials_list_reports_bindings(client, case, workflow, materials, fake):
    body = client.get(f"/api/cases/{case['id']}/materials").json()
    by_id = {asset["id"]: asset for asset in body["assets"]}

    image_refs = by_id[materials["image"]["id"]]["references"]
    assert {entry["step_name"] for entry in image_refs["workflows"]} == {
        "First reading",
        "Revision in response",
    }

    article_refs = by_id[materials["article"]["id"]]["references"]
    assert [entry["step_name"] for entry in article_refs["workflows"]] == ["Literature response"]
    assert by_id[materials["article"]["id"]]["text_chars"] == len(ARTICLE_TEXT)


def test_materials_list_counts_runs_that_used_the_material(client, case, workflow, materials, fake):
    client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    body = client.get(f"/api/cases/{case['id']}/materials").json()
    by_id = {asset["id"]: asset for asset in body["assets"]}
    assert by_id[materials["image"]["id"]]["references"]["runs"] == 1


def test_rename_changes_title_and_provenance_only(client, case, materials):
    response = client.patch(
        f"/api/assets/{materials['article']['id']}",
        json={"title": "Renamed note", "provenance": "researcher, 2024"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed note"

    detail = client.get(f"/api/assets/{materials['article']['id']}").json()
    assert detail["title"] == "Renamed note"
    assert detail["provenance"] == "researcher, 2024"
    assert "Later colophons" in detail["text"], "the text must not be touched"

    other = client.get(f"/api/assets/{materials['image']['id']}").json()
    assert other["title"] == "Detail of the first episode"


def test_delete_unbinds_every_step_and_bumps_the_version(client, case, workflow, materials):
    response = client.delete(f"/api/assets/{materials['article']['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == materials["article"]["id"]
    assert [entry["step_name"] for entry in body["unbound_from"]] == ["Literature response"]
    assert body["file_removed"] is True

    workflow_after = client.get(f"/api/workflows/{workflow['id']}").json()
    assert workflow_after["version"] == workflow["version"] + 1
    assert all(
        materials["article"]["id"] not in step["material_ids"]
        for step in workflow_after["definition"]["steps"]
    )

    assert client.get(f"/api/assets/{materials['article']['id']}").status_code == 404
    listed = client.get(f"/api/cases/{case['id']}/materials").json()["assets"]
    assert materials["article"]["id"] not in {asset["id"] for asset in listed}


def test_delete_removes_the_stored_file_once(client, case, materials):
    path = Path(_stored_path(materials["image"]["id"]))
    assert path.is_file()
    client.delete(f"/api/assets/{materials['image']['id']}")
    assert not path.exists()


def test_deleting_one_of_two_identical_uploads_keeps_the_file(client, case, materials):
    duplicate = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "image", "title": "same bytes"},
        files={"file": ("copy.png", PNG_1PX, "image/png")},
    ).json()
    path = Path(_stored_path(duplicate["id"]))

    result = client.delete(f"/api/assets/{duplicate['id']}").json()
    assert result["file_removed"] is False
    assert path.is_file(), "another material still points at this file"

    client.delete(f"/api/assets/{materials['image']['id']}")
    assert not path.exists(), "the last reference removes the file"


def test_delete_unknown_material_is_a_404(client, case):
    assert client.delete("/api/assets/mat_missing").status_code == 404


def test_deleted_material_leaves_the_workflow_runnable_after_rebinding(client, case, workflow, materials, fake):
    """A second article can be bound after the first is deleted; the step is not stuck."""
    replacement = client.post(
        f"/api/cases/{case['id']}/assets",
        data={"kind": "article", "title": "second note", "pasted_text": "A different note."},
    ).json()
    client.delete(f"/api/assets/{materials['article']['id']}")

    definition = client.get(f"/api/workflows/{workflow['id']}").json()["definition"]
    for step in definition["steps"]:
        if step["name"] == "Literature response":
            step["material_ids"] = [replacement["id"]]
    assert client.put(f"/api/workflows/{workflow['id']}", json=definition).status_code == 200

    run = client.post("/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]})
    assert run.status_code == 200, run.text
    assert run.json()["run"]["status"] == "awaiting_human"
