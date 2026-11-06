"""Validation of model output.

A model response is untrusted input. Structure, cited asset ids, image regions, passage
bounds, and references to earlier claims are all checked against what the step actually
received. A reference that resolves is not proof that the source supports the claim;
the researcher inspects the underlying material in the read view.
"""

from __future__ import annotations

import json
from typing import Any

from .schemas import AgentOutputIn, EvidenceItemIn, new_id


class OutputError(ValueError):
    """Model output that the runtime refuses to store as a reading."""


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_output(
    raw: str,
    *,
    allowed_assets: dict[str, dict[str, Any]],
    asset_text_lengths: dict[str, int],
    referenced_assets: set[str] | None = None,
    prior_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse and validate one agent response.

    ``allowed_assets`` are the materials bound to this step. ``referenced_assets`` may
    name further assets that earlier records already cited; those can be named but their
    text was not supplied here, so quoting a passage from them is refused.
    """
    text = _strip_code_fence(raw)
    if not text:
        raise OutputError("the model returned an empty response")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutputError(f"the model response is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise OutputError("the model response must be a JSON object")

    try:
        parsed = AgentOutputIn.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise OutputError(f"the model response does not match the required shape: {exc}") from exc

    referenced = referenced_assets or set()
    prior = prior_index or {}
    able_to_name = set(allowed_assets) | referenced

    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in parsed.evidence:
        record = _validate_item(
            item,
            allowed_assets=allowed_assets,
            able_to_name=able_to_name,
            asset_text_lengths=asset_text_lengths,
            prior=prior,
            earlier=seen_ids,
        )
        seen_ids.add(record["id"])
        evidence.append(record)

    return {
        "note": parsed.note.strip(),
        "evidence": evidence,
        "unresolved": [line.strip() for line in parsed.unresolved if line.strip()],
    }


def _validate_item(
    item: EvidenceItemIn,
    *,
    allowed_assets: dict[str, dict[str, Any]],
    able_to_name: set[str],
    asset_text_lengths: dict[str, int],
    prior: dict[str, dict[str, Any]],
    earlier: set[str],
) -> dict[str, Any]:
    asset_id = item.asset_id
    kind = None

    if asset_id is not None:
        if asset_id not in able_to_name:
            raise OutputError(
                f"evidence names material {asset_id!r}, which this step was not given"
            )
        bound = allowed_assets.get(asset_id)
        kind = (bound or {}).get("kind")

    if item.region is not None:
        if asset_id is None or kind != "image":
            raise OutputError("an image region can only be given for an image bound to this step")
        if item.region.x + item.region.width > 1.0001 or item.region.y + item.region.height > 1.0001:
            raise OutputError("an image region must stay inside the frame (0..1 coordinates)")

    if item.passage is not None:
        if asset_id is None or kind not in {"article", "note"}:
            raise OutputError("a passage can only be given for a text bound to this step")
        if item.passage.start > item.passage.end:
            raise OutputError("a passage must have start <= end")
        length = asset_text_lengths.get(asset_id)
        if length is None:
            raise OutputError("a passage was given for text this step did not receive")
        if item.passage.end > length:
            raise OutputError("a passage extends past the end of the supplied text")

    for reference in item.refers_to:
        if reference in earlier:
            continue
        if reference in prior:
            entry = prior[reference]
            if entry.get("kind") == "evidence" and entry.get("record_id") is not None:
                continue
            if entry.get("kind") == "record":
                continue
        raise OutputError(f"evidence refers to {reference!r}, which does not exist earlier in this run")

    return {
        "id": new_id("ev"),
        "type": item.type.value,
        "text": item.text,
        "asset_id": asset_id,
        "region": item.region.model_dump() if item.region else None,
        "passage": item.passage.model_dump() if item.passage else None,
        "refers_to": list(item.refers_to),
    }


OUTPUT_CONTRACT = """Reply with one JSON object and nothing else:
{
  "note": "a short readable note in the language of the supplied material",
  "evidence": [
    {
      "type": "observation | source_report | interpretation | question",
      "text": "one claim",
      "asset_id": "id of a material you were given, or null",
      "region": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
      "passage": {"start": 0, "end": 0},
      "refers_to": ["id of an evidence item or step record you were given"]
    }
  ],
  "unresolved": ["what is still open or disputed"]
}
Rules: use only the materials listed in this message; never cite an article, author,
page, or quotation that was not supplied; name an image region only for a supplied image
and only within the visible frame; a passage must be a character range inside supplied
text; if the evidence does not settle a question, say so under "unresolved" instead of
concluding."""
