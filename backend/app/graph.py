"""Workflow validation.

A workflow is a directed sequence of agent and human steps. Nothing here looks at step
names: permission comes from a step's explicit material bindings, and inheritance comes
from edges. A label such as "A" or "B" carries no behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import EdgeIn, StepIn, StepKind, WorkflowIn


class WorkflowError(ValueError):
    """A workflow definition the runtime refuses to run."""


@dataclass
class PlannedStep:
    step: dict[str, Any]
    ordinal: int
    upstream: list[str]  # step ids whose outputs are handed to this step


@dataclass
class Plan:
    steps: list[PlannedStep]
    edges: list[dict[str, Any]]

    def step_ids(self) -> list[str]:
        return [item.step["id"] for item in self.steps]


def _normalise_ids(workflow: WorkflowIn) -> tuple[list[StepIn], list[EdgeIn]]:
    steps = list(workflow.steps)
    seen: set[str] = set()
    for index, step in enumerate(steps):
        if not step.id:
            step.id = f"step{index + 1}"
        if step.id in seen:
            raise WorkflowError(f"duplicate step id: {step.id}")
        seen.add(step.id)

    edges = list(workflow.edges)
    used: set[str] = set()
    for index, edge in enumerate(edges):
        if not edge.id:
            edge.id = f"edge{index + 1}"
        if edge.id in used:
            raise WorkflowError(f"duplicate edge id: {edge.id}")
        used.add(edge.id)
    return steps, edges


def validate_workflow(
    workflow: WorkflowIn,
    *,
    material_ids: set[str],
    profile_ids: set[str],
    asset_kinds: dict[str, str],
) -> Plan:
    """Check a workflow against the case's actual materials and stored profiles."""
    steps, edges = _normalise_ids(workflow)
    step_map = {step.id: step for step in steps}

    for step in steps:
        if step.kind is StepKind.agent:
            if step.profile_id not in profile_ids:
                raise WorkflowError(f"step {step.name!r} refers to an unknown agent profile")
        for material_id in step.material_ids:
            if material_id not in material_ids:
                raise WorkflowError(
                    f"step {step.name!r} binds a material that is not in this case"
                )
        if step.kind is StepKind.human and not step.human_prompt.strip():
            raise WorkflowError(f"human step {step.name!r} needs a prompt for the researcher")

    for edge in edges:
        if edge.source not in step_map:
            raise WorkflowError(f"edge {edge.id} starts at an unknown step")
        if edge.target not in step_map:
            raise WorkflowError(f"edge {edge.id} ends at an unknown step")
        if edge.source == edge.target:
            raise WorkflowError(f"edge {edge.id} points at its own step")

    outgoing: dict[str, list[str]] = {step.id: [] for step in steps}
    indegree: dict[str, int] = {step.id: 0 for step in steps}
    for edge in edges:
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1

    for step_id, count in indegree.items():
        label = step_map[step_id].name
        if count > 1:
            raise WorkflowError(
                f"step {label!r} has more than one incoming hand-off; "
                "this version supports a single sequence"
            )
        if len(outgoing[step_id]) > 1:
            raise WorkflowError(
                f"step {step_map[step_id].name!r} hands off to more than one step; "
                "this version supports a single sequence"
            )

    # Deterministic topological order; ties broken by the order the user authored.
    order = {step.id: index for index, step in enumerate(steps)}
    ready = [step.id for step in steps if indegree[step.id] == 0]
    ready.sort(key=lambda sid: order[sid])
    planned: list[PlannedStep] = []
    upstream: dict[str, list[str]] = {step.id: [] for step in steps}
    while ready:
        current = ready.pop(0)
        planned.append(PlannedStep(step=step_map[current].model_dump(mode="json"), ordinal=len(planned), upstream=upstream[current]))
        for target in outgoing[current]:
            upstream[target].append(current)
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=lambda sid: order[sid])

    if len(planned) != len(steps):
        raise WorkflowError("the workflow contains a cycle; this version requires a sequence")

    return Plan(steps=planned, edges=[edge.model_dump(mode="json") for edge in edges])


def default_template(case_id: str, materials: list[dict], profile_ids: list[str]) -> dict:
    """The image → literature → researcher → return template from the design document.

    This is a starting point the researcher can edit, not a privileged flow. Images go to
    the reading steps and texts to the literature step, chosen by material kind rather
    than by upload order.
    """
    images = [item["id"] for item in materials if item.get("kind") == "image"][:1]
    texts = [item["id"] for item in materials if item.get("kind") in {"article", "note"}]
    reader = profile_ids[0] if profile_ids else None
    responder = profile_ids[1] if len(profile_ids) > 1 else reader

    steps = [
        {
            "id": "step1",
            "name": "First reading",
            "kind": "agent",
            "profile_id": reader,
            "material_ids": images,
            "human_prompt": "",
            "position": {"x": 0.0, "y": 0.0},
        },
        {
            "id": "step2",
            "name": "Literature response",
            "kind": "agent",
            "profile_id": responder,
            "material_ids": texts,
            "human_prompt": "",
            "position": {"x": 260.0, "y": 0.0},
        },
        {
            "id": "step3",
            "name": "Researcher question",
            "kind": "human",
            "profile_id": None,
            "material_ids": [],
            "human_prompt": "What should the reading answer next? Name the claim you doubt.",
            "position": {"x": 520.0, "y": 0.0},
        },
        {
            "id": "step4",
            "name": "Revision in response",
            "kind": "agent",
            "profile_id": reader,
            "material_ids": images,
            "human_prompt": "",
            "position": {"x": 780.0, "y": 0.0},
        },
    ]
    edges = [
        {"id": "edge1", "source": "step1", "target": "step2", "passes_output": True},
        {"id": "edge2", "source": "step2", "target": "step3", "passes_output": True},
        {"id": "edge3", "source": "step3", "target": "step4", "passes_output": True},
    ]
    return {"name": "Image, literature, return", "case_id": case_id, "steps": steps, "edges": edges}


DEFAULT_PROFILES = [
    {
        "name": "Image reader",
        "role_instructions": (
            "You read a work of visual culture from the image and its title alone. "
            "Separate what is visible from what the title suggests and from your interpretation. "
            "Describe only what is inside the visible frame; never claim to see what a crop might "
            "have excluded. Where evidence is thin, say so and list it under unresolved."
        ),
        "expected_response": "Visible detail, title-led association, interpretation, open questions.",
    },
    {
        "name": "Literature respondent",
        "role_instructions": (
            "You respond to another reader's claims using only the articles supplied in this step. "
            "Cite the article you rely on and quote its wording where it matters. "
            "Do not add sources, authors, or page numbers that were not supplied, and do not "
            "invent quotations. Name where the supplied literature disagrees with the reader, "
            "and leave the disagreement visible."
        ),
        "expected_response": "Sourced points, agreement or challenge, questions for the researcher.",
    },
]
