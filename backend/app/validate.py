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

    A response that is not a usable JSON object fails the step: there is nothing to keep.
    Individual evidence items that cite material this step never received are dropped and
    reported under ``rejected`` instead, so the readable note and the claims that do
    resolve survive. The researcher needs to see both what the model said and what the
    runtime refused.

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
        raise OutputError(
            f"the model response does not match the required shape: {_describe(exc)}"
        ) from exc

    referenced = referenced_assets or set()
    prior = prior_index or {}
    able_to_name = set(allowed_assets) | referenced

    evidence: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for raw_item in parsed.evidence:
        if not isinstance(raw_item, dict):
            rejected.append(
                {
                    "type": "unknown",
                    "text": str(raw_item)[:400],
                    "reason": "an evidence item must be a JSON object",
                }
            )
            continue

        try:
            item = EvidenceItemIn.model_validate(raw_item)
        except Exception as exc:  # pydantic ValidationError on this single item
            rejected.append(
                {
                    "type": str(raw_item.get("type", "unknown"))[:40],
                    "text": str(raw_item.get("text", ""))[:400],
                    "reason": _describe(exc),
                }
            )
            continue

        try:
            record = _validate_item(
                item,
                allowed_assets=allowed_assets,
                able_to_name=able_to_name,
                asset_text_lengths=asset_text_lengths,
                prior=prior,
                earlier=seen_ids,
            )
        except OutputError as exc:
            rejected.append(
                {
                    "type": item.type.value,
                    "text": item.text[:400],
                    "reason": str(exc),
                }
            )
            continue
        seen_ids.add(record["id"])
        evidence.append(record)

    return {
        "note": parsed.note.strip(),
        "evidence": evidence,
        "unresolved": [
            line.strip() for line in parsed.unresolved if isinstance(line, str) and line.strip()
        ],
        "rejected": rejected,
    }


def _describe(exc: Exception, limit: int = 3) -> str:
    """A short, readable reason for one rejected item instead of a pydantic dump."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            items = errors()
        except Exception:  # noqa: BLE001 - never let reporting itself fail
            items = []
        if items:
            parts = []
            for item in items[:limit]:
                location = ".".join(str(part) for part in item.get("loc", ())) or "value"
                message = str(item.get("msg", "is not valid"))
                parts.append(f"{location} {message}".strip())
            suffix = f" (and {len(items) - limit} more)" if len(items) > limit else ""
            return "; ".join(parts) + suffix
    return str(exc)


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
      "refers_to": ["id of an evidence item or step record you were given"]
    }
  ],
  "unresolved": ["what is still open or disputed"]
}

Two optional keys may be added to an evidence item, and only when they are real:
- "region": {"x": 0.10, "y": 0.10, "width": 0.30, "height": 0.30} — where the detail sits
  inside the supplied image, as fractions 0..1 measured from the top-left corner. The
  numbers here are only an illustration; choose the ones that match what you describe.
  Width and height must be greater than zero, and the box must stay inside the frame.
  Leave the key out when you cannot place the detail. Use x 0, y 0, width 1, height 1
  only when the claim really is about the entire frame.
- "passage": {"start": 12, "end": 48} — character offsets into the supplied text. Leave
  the key out unless you are pointing at a specific span of that text.

Rules: use only the materials listed in this message; never name a material that is not
listed above; never cite an article, author, page, or quotation that was not supplied; if
the evidence does not settle a question, say so under "unresolved" instead of concluding."""
