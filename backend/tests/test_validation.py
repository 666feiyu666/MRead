"""Acceptance 6 and 7: untrusted output is checked, and bad output fails the step."""

from __future__ import annotations

import json


def test_invented_material_fails_the_step(client, case, workflow, fake):
    fake.push(
        json.dumps(
            {
                "note": "A confident reading.",
                "evidence": [
                    {
                        "type": "source_report",
                        "text": "Page 42 of the catalogue says so.",
                        "asset_id": "mat_invented",
                    }
                ],
                "unresolved": [],
            }
        )
    )
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()

    assert detail["run"]["status"] == "failed"
    first = detail["records"][0]
    assert first["status"] == "failed"
    assert "not given" in first["error"]
    # A failed step is not turned into a research note.
    assert first["output"] == {}


def test_region_outside_the_frame_is_refused():
    from app.validate import OutputError, parse_output

    raw = json.dumps(
        {
            "note": "n",
            "evidence": [
                {
                    "type": "observation",
                    "text": "t",
                    "asset_id": "mat_img",
                    "region": {"x": 0.8, "y": 0.1, "width": 0.5, "height": 0.2},
                }
            ],
        }
    )
    try:
        parse_output(
            raw,
            allowed_assets={"mat_img": {"id": "mat_img", "kind": "image"}},
            asset_text_lengths={},
        )
    except OutputError as exc:
        assert "inside the frame" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an out-of-frame region must be refused")


def test_passage_past_the_end_of_the_text_is_refused():
    from app.validate import OutputError, parse_output

    raw = json.dumps(
        {
            "note": "n",
            "evidence": [
                {
                    "type": "source_report",
                    "text": "t",
                    "asset_id": "mat_art",
                    "passage": {"start": 10, "end": 5000},
                }
            ],
        }
    )
    try:
        parse_output(
            raw,
            allowed_assets={"mat_art": {"id": "mat_art", "kind": "article"}},
            asset_text_lengths={"mat_art": 100},
        )
    except OutputError as exc:
        assert "past the end" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an out-of-range passage must be refused")


def test_reference_to_an_unknown_claim_is_refused():
    from app.validate import OutputError, parse_output

    raw = json.dumps(
        {
            "note": "n",
            "evidence": [
                {"type": "interpretation", "text": "t", "refers_to": ["ev_missing"]}
            ],
        }
    )
    try:
        parse_output(raw, allowed_assets={}, asset_text_lengths={})
    except OutputError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a dangling reference must be refused")


def test_non_json_output_fails_the_step(client, case, workflow, fake):
    fake.push("I think this is a Ming forgery.")
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()
    assert detail["run"]["status"] == "failed"
    assert "not valid JSON" in detail["records"][0]["error"]


def test_unresolved_claims_are_kept_visible(client, case, workflow, fake):
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()
    first = detail["records"][0]
    assert first["output"]["unresolved"], "disagreement must survive validation"
    assert first["output"]["evidence"]


def test_evidence_can_reference_an_earlier_record(client, case, workflow, fake):
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()
    first_record_id = detail["records"][0]["id"]
    assert first_record_id  # the record id is what later steps cite
    second_payload = detail["records"][1]["payload"]
    assert second_payload["prior_step_ids"] == ["step1"]
