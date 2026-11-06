"""Model providers.

A provider receives one fully assembled request and returns raw text. It never decides
what a step may see; that is the scheduler's job. Responses are untrusted and are
parsed elsewhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import config


class ProviderError(RuntimeError):
    """A model call failed. The message is safe to show to the researcher."""


@dataclass
class ImagePart:
    asset_id: str
    data: bytes
    mime: str


@dataclass
class ModelRequest:
    model: str
    system: str
    user_text: str
    images: list[ImagePart] = field(default_factory=list)

    def record(self) -> dict[str, Any]:
        """What the run record keeps: ids only, never image bytes or full text."""
        return {
            "model": self.model,
            "image_asset_ids": [image.asset_id for image in self.images],
            "user_text_chars": len(self.user_text),
            "system_chars": len(self.system),
            "system": self.system,
            "user_text": self.user_text,
        }


class Provider(Protocol):
    name: str

    def complete(self, request: ModelRequest) -> str: ...


class FakeProvider:
    """Deterministic provider used to test routing, state, and validation.

    It records every request it receives, so tests can prove which materials and prior
    steps were actually handed to a call.
    """

    name = "fake"

    def __init__(self, outputs: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._outputs = list(outputs or [])

    def push(self, output: str) -> None:
        self._outputs.append(output)

    def complete(self, request: ModelRequest) -> str:
        self.calls.append(request.record())
        if self._outputs:
            return self._outputs.pop(0)
        return self._default_output(request)

    def _default_output(self, request: ModelRequest) -> str:
        evidence: list[dict[str, Any]] = []
        materials: list[tuple[str, str]] = []
        for line in request.user_text.splitlines():
            if not line.startswith("MATERIAL asset_id="):
                continue
            fields = dict(token.split("=", 1) for token in line.split() if "=" in token)
            materials.append((fields.get("asset_id", ""), fields.get("kind", "")))
        image_ids = [material_id for material_id, kind in materials if kind == "image"]
        text_ids = [material_id for material_id, kind in materials if kind in {"article", "note"}]
        if image_ids:
            evidence.append(
                {
                    "type": "observation",
                    "text": f"Visible in the supplied image ({image_ids[0]}): "
                    "the frame shows a seated group.",
                    "asset_id": image_ids[0],
                    "region": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
                }
            )
        if text_ids:
            evidence.append(
                {
                    "type": "source_report",
                    "text": f"The supplied text ({text_ids[0]}) discusses the work's date.",
                    "asset_id": text_ids[0],
                    "passage": {"start": 0, "end": min(40, _text_length(request.user_text, text_ids[0]))},
                }
            )
        evidence.append(
            {
                "type": "interpretation",
                "text": "The gathering reads as a deliberately staged scene rather than a record.",
                "refers_to": [],
            }
        )
        step_name = ""
        for line in request.user_text.splitlines():
            if line.startswith("STEP: "):
                step_name = line[len("STEP: ") :].strip()
                break
        has_decision = "RESEARCHER DECISION" in request.user_text
        note = (
            f"Fake reading for {step_name or 'this step'} under {request.model}. "
            "Nothing is inferred outside the frame."
        )
        if has_decision:
            note = f"Fake revision for {step_name or 'this step'} after the researcher's question."
        return json.dumps(
            {
                "note": note,
                "evidence": evidence,
                "unresolved": ["Whether the frame is a full work or a detail remains open."],
            },
            ensure_ascii=False,
        )


def _text_length(user_text: str, asset_id: str) -> int:
    """Read the character count the scheduler declared for a supplied text."""
    marker = f"--- text of {asset_id} (characters 0.."
    for line in user_text.splitlines():
        if line.startswith(marker):
            digits = line[len(marker) :].split(")", 1)[0]
            if digits.isdigit():
                return int(digits)
    return 0


class OpenAICompatibleProvider:
    """Any OpenAI-compatible chat completions endpoint (DeepSeek by default).

    Each call is independent: no conversation history is reused between steps.
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.OPENAI_API_KEY
        self.base_url = (base_url or config.OPENAI_BASE_URL).rstrip("/")
        self.timeout = timeout or config.REQUEST_TIMEOUT

    def complete(self, request: ModelRequest) -> str:
        import base64

        import httpx

        if not self.api_key:
            raise ProviderError(
                "no model key is configured on the server; set DEEPSEEK_API_KEY in .env"
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": request.user_text}]
        for image in request.images:
            encoded = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.mime};base64,{encoded}"},
                }
            )

        body = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"the model endpoint could not be reached: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            detail = _safe_detail(response)
            raise ProviderError(f"the model endpoint refused the call ({response.status_code}): {detail}")

        try:
            payload = response.json()
            message = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError("the model endpoint returned an unexpected response") from exc
        if not isinstance(message, str) or not message.strip():
            raise ProviderError("the model returned an empty response")
        return message


def _safe_detail(response: Any) -> str:
    """Extract an error message without echoing credentials or request bodies."""
    try:
        data = response.json()
    except ValueError:
        return "no readable error body"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:400]
        if isinstance(error, str):
            return error[:400]
    return "no readable error body"


def build_provider(kind: str | None = None, *, outputs: list[str] | None = None) -> Provider:
    choice = (kind or config.PROVIDER).lower()
    if choice == "fake":
        return FakeProvider(outputs=outputs)
    if choice in {"openai", "deepseek"}:
        return OpenAICompatibleProvider()
    raise ProviderError(f"unknown provider: {kind}")
