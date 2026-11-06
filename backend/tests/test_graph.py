"""Workflow validation: bindings, not names, decide what a step may see."""

from __future__ import annotations

import pytest

from app.graph import WorkflowError, validate_workflow
from app.schemas import WorkflowIn


def _workflow(steps, edges):
    return WorkflowIn.model_validate({"name": "w", "case_id": "case_1", "steps": steps, "edges": edges})


def _step(step_id, *, kind="agent", profile_id="prof_1", materials=(), prompt=""):
    return {
        "id": step_id,
        "name": step_id,
        "kind": kind,
        "profile_id": profile_id if kind == "agent" else None,
        "material_ids": list(materials),
        "human_prompt": prompt,
    }


def test_unknown_material_is_refused():
    with pytest.raises(WorkflowError, match="not in this case"):
        validate_workflow(
            _workflow([_step("s1", materials=["mat_ghost"])], []),
            material_ids={"mat_real"},
            profile_ids={"prof_1"},
            asset_kinds={"mat_real": "image"},
        )


def test_unknown_profile_is_refused():
    with pytest.raises(WorkflowError, match="unknown agent profile"):
        validate_workflow(
            _workflow([_step("s1", profile_id="prof_ghost")], []),
            material_ids=set(),
            profile_ids={"prof_1"},
            asset_kinds={},
        )


def test_cycle_is_refused():
    with pytest.raises(WorkflowError, match="cycle"):
        validate_workflow(
            _workflow(
                [_step("s1"), _step("s2")],
                [
                    {"source": "s1", "target": "s2"},
                    {"source": "s2", "target": "s1"},
                ],
            ),
            material_ids=set(),
            profile_ids={"prof_1"},
            asset_kinds={},
        )


def test_branching_is_refused():
    with pytest.raises(WorkflowError, match="more than one"):
        validate_workflow(
            _workflow(
                [_step("s1"), _step("s2"), _step("s3")],
                [
                    {"source": "s1", "target": "s2"},
                    {"source": "s1", "target": "s3"},
                ],
            ),
            material_ids=set(),
            profile_ids={"prof_1"},
            asset_kinds={},
        )


def test_human_step_needs_a_prompt():
    with pytest.raises(WorkflowError, match="needs a prompt"):
        validate_workflow(
            _workflow([_step("s1", kind="human", prompt="")], []),
            material_ids=set(),
            profile_ids={"prof_1"},
            asset_kinds={},
        )


def test_order_follows_edges_not_listing():
    plan = validate_workflow(
        _workflow(
            [_step("late"), _step("early")],
            [{"source": "early", "target": "late"}],
        ),
        material_ids=set(),
        profile_ids={"prof_1"},
        asset_kinds={},
    )
    assert [item.step["id"] for item in plan.steps] == ["early", "late"]
    assert plan.steps[1].upstream == ["early"]
