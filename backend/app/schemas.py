"""Pydantic models for the parts of MRead that cross a trust boundary.

Material uploading, workflow definitions, and model responses all arrive as untrusted
input, so they are parsed into these shapes before anything is stored or scheduled.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AssetKind(str, Enum):
    image = "image"
    article = "article"
    note = "note"


class EvidenceType(str, Enum):
    observation = "observation"
    source_report = "source_report"
    interpretation = "interpretation"
    question = "question"


class StepKind(str, Enum):
    agent = "agent"
    human = "human"


RunStatus = Literal["queued", "running", "awaiting_human", "completed", "failed"]
RecordStatus = Literal["pending", "running", "completed", "awaiting_human", "failed", "skipped"]


# --------------------------------------------------------------------------- inputs


class CaseIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=20000)


class AgentProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role_instructions: str = Field(min_length=1, max_length=20000)
    model: str = Field(default="", max_length=120)
    expected_response: str = Field(default="", max_length=4000)


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


class Passage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class StepIn(BaseModel):
    id: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    kind: StepKind = StepKind.agent
    profile_id: str | None = None
    material_ids: list[str] = Field(default_factory=list)
    # For human steps: the question or decision the researcher is invited to make.
    human_prompt: str = Field(default="", max_length=2000)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})

    @model_validator(mode="after")
    def _check(self) -> "StepIn":
        if self.kind is StepKind.agent and not self.profile_id:
            raise ValueError("an agent step needs a profile_id")
        if self.kind is StepKind.human and self.profile_id:
            raise ValueError("a human step does not invoke a profile")
        return self


class EdgeIn(BaseModel):
    id: str = Field(default="", max_length=64)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    passes_output: bool = True


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    case_id: str = Field(min_length=1)
    steps: list[StepIn] = Field(min_length=1)
    edges: list[EdgeIn] = Field(default_factory=list)


class RunIn(BaseModel):
    case_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)


class DecisionIn(BaseModel):
    step_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=8000)


# -------------------------------------------------------------------------- outputs


class EvidenceItemIn(BaseModel):
    """One structured claim produced by an agent step."""

    model_config = ConfigDict(extra="allow")

    type: EvidenceType
    text: str = Field(min_length=1, max_length=4000)
    asset_id: str | None = None
    region: Region | None = None
    passage: Passage | None = None
    refers_to: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class AgentOutputIn(BaseModel):
    """The JSON contract every agent step must return."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=20000)
    evidence: list[EvidenceItemIn] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class HumanDecisionOut(BaseModel):
    step_id: str
    text: str


def dump(model: Any) -> dict[str, Any]:
    """Serialize a pydantic model to plain JSON-safe data."""
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json")
    return model
