"""Acceptance 6 and 7: untrusted output is checked, and bad output is reported clearly.

An evidence item that cites material the step never received is dropped and listed under
``rejected``; the rest of the reading (note, valid claims, open questions) survives. Only
a response that cannot be read at all fails the step.
"""

from __future__ import annotations

import json


def test_invented_material_is_rejected_and_the_step_still_completes(client, case, workflow, fake):
    fake.push(
        json.dumps(
            {
                "note": "A confident reading, with one unsupported citation.",
                "evidence": [
                    {
                        "type": "source_report",
                        "text": "Page 42 of the catalogue says so.",
                        "asset_id": "mat_invented",
                    },
                    {
                        "type": "interpretation",
                        "text": "The gathering reads as staged.",
                        "refers_to": [],
                    },
                ],
                "unresolved": ["Whether the frame is a detail."],
            }
        )
    )
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()

    first = detail["records"][0]
    assert first["status"] == "completed"
    assert first["output"]["note"].startswith("A confident reading")
    assert [item["type"] for item in first["output"]["evidence"]] == ["interpretation"]
    assert len(first["output"]["rejected"]) == 1
    assert "not given" in first["output"]["rejected"][0]["reason"]
    assert first["output"]["rejected"][0]["text"].startswith("Page 42")


def test_region_outside_the_frame_is_rejected():
    from app.validate import parse_output

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
    output = parse_output(
        raw,
        allowed_assets={"mat_img": {"id": "mat_img", "kind": "image"}},
        asset_text_lengths={},
    )
    assert output["evidence"] == []
    assert "inside the frame" in output["rejected"][0]["reason"]


def test_passage_past_the_end_of_the_text_is_rejected():
    from app.validate import parse_output

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
    output = parse_output(
        raw,
        allowed_assets={"mat_art": {"id": "mat_art", "kind": "article"}},
        asset_text_lengths={"mat_art": 100},
    )
    assert "past the end" in output["rejected"][0]["reason"]


def test_reference_to_an_unknown_claim_is_rejected():
    from app.validate import parse_output

    raw = json.dumps(
        {
            "note": "n",
            "evidence": [{"type": "interpretation", "text": "t", "refers_to": ["ev_missing"]}],
        }
    )
    output = parse_output(raw, allowed_assets={}, asset_text_lengths={})
    assert "does not exist" in output["rejected"][0]["reason"]


def test_non_json_output_still_fails_the_step(client, case, workflow, fake):
    fake.push("I think this is a Ming forgery.")
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()
    assert detail["run"]["status"] == "failed"
    assert "not valid JSON" in detail["records"][0]["error"]
    assert detail["records"][0]["output"] == {}


def test_zero_size_region_is_rejected_without_losing_the_reading():
    """A model that fills the shape example with 0×0 boxes must not lose its note."""
    from app.validate import parse_output

    raw = json.dumps(
        {
            "note": "Two claims, one with a placeholder box.",
            "evidence": [
                {
                    "type": "observation",
                    "text": "A figure stands at the left.",
                    "asset_id": "mat_img",
                    "region": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
                },
                {"type": "observation", "text": "Two hands are visible.", "asset_id": "mat_img"},
            ],
            "unresolved": ["Whether the print is complete."],
        }
    )
    output = parse_output(
        raw,
        allowed_assets={"mat_img": {"id": "mat_img", "kind": "image"}},
        asset_text_lengths={},
    )
    assert output["note"].startswith("Two claims")
    assert [item["text"] for item in output["evidence"]] == ["Two hands are visible."]
    assert len(output["rejected"]) == 1
    assert "greater than 0" in output["rejected"][0]["reason"]
    assert output["unresolved"] == ["Whether the print is complete."]


def test_malformed_evidence_items_are_rejected_one_by_one():
    from app.validate import parse_output

    raw = json.dumps(
        {
            "note": "Mixed bag.",
            "evidence": [
                "a bare string instead of an object",
                {"type": "claim", "text": "unknown claim type"},
                {"type": "observation", "text": "Fine.", "asset_id": "mat_img"},
            ],
        }
    )
    output = parse_output(
        raw,
        allowed_assets={"mat_img": {"id": "mat_img", "kind": "image"}},
        asset_text_lengths={},
    )
    assert [item["text"] for item in output["evidence"]] == ["Fine."]
    assert len(output["rejected"]) == 2
    assert "must be a JSON object" in output["rejected"][0]["reason"]


def test_missing_note_still_fails_the_step_with_a_short_message(client, case, workflow, fake):
    fake.push(json.dumps({"evidence": [{"type": "observation", "text": "no note here"}]}))
    detail = client.post(
        "/api/runs", json={"case_id": case["id"], "workflow_id": workflow["id"]}
    ).json()
    record = detail["records"][0]
    assert record["status"] == "failed"
    assert "required shape" in record["error"]
    assert "note" in record["error"]
    assert len(record["error"]) < 300, "the error must be readable, not a pydantic dump"


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
