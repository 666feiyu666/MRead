# A Visual-Culture Reading Desk: MVP Design

## Goal

A researcher uploads an image, gives it a title, and uploads or pastes an article of their own choosing. The system keeps three ordered working records: A's first reading, B's response from the literature, and A's revision after the researcher's follow-up question. The interface lets the researcher check whether a given claim comes from the image, from the title, or from the article, and it preserves disagreements that remain unresolved.

The *Night Revels of Han Xizai* reproduction supplied with this brief is a design sample, not built-in material. What a user uploads may be a complete handscroll or only a detail; the system must never infer what lies outside the frame from a cropped view.

## References and trade-offs

The primary reference is [ChatDev 2.0](https://github.com/OpenBMB/ChatDev): nodes have explicit responsibilities, edges control message hand-off, the run is observable, and human nodes decide the path forward. Its [tutorial](https://github.com/OpenBMB/ChatDev/blob/main/frontend/public/tutorial-en.md) demonstrates parallel nodes, context scoping, and human feedback; the [backend documentation](https://github.com/OpenBMB/ChatDev/blob/main/docs/user_guide/en/index.md) shows the boundaries of the web UI, the run service, status streaming, and session records.

The first release uses a fixed A → B → researcher → A sequence. The interface centres on the image and the evidence, and shows a compact stage track; it offers no general workflow editor, no arbitrary tool execution, and no automatic literature search.

## Roles and information boundaries

| Stage | Input | Output | Constraint |
| --- | --- | --- | --- |
| A, first reading | The user's image and title | Visible details, associations carried by the title, a preliminary interpretation, open questions | Receives no article; visible content and interpretation are written separately |
| B, literature response | The article(s) supplied by the user, A's complete first reading | Sourced points from the literature, support for or challenges to A's judgements, questions for the researcher | Cites only the article(s) supplied in this run; must not invent page numbers, authors, or material that was not provided |
| Researcher decision | The raw records from A and B | One follow-up question or request for review | The human decides the direction of inquiry; disagreements may be left standing |
| A, revision | The original image, title, A's first reading, B's response, the researcher's question | What changed, what was kept, what still cannot be determined | Must not overwrite the first reading; must state the basis for every change |

The choice of article belongs to the user. B does not search the internet and does not add sources on its own. A and B may call the same image-capable model, but each call uses an independent context and a different input set.

## User flow

1. The user uploads a PNG, JPEG, or WebP image and gives it a title; then uploads an article as a text-extractable PDF, TXT, or MD file, or pastes the article text, with an article title and an optional source. Scanned PDFs are not OCR'd for now; the user is prompted to paste the text instead.
2. The backend validates the input, creates a `run_id`, and stores the image and the text the user supplied.
3. A reads the image and title first; the first reading is validated and saved, after which B receives that reading plus the article and produces a response.
4. The frontend presents A's and B's records, their citations, and the run status. The user writes one follow-up question.
5. A performs one revision; the frontend keeps the first reading, B's response, and the revision side by side, and the record remains available after a page reload.

A run contains at most one researcher follow-up. Further rounds, multi-user collaboration, and research project management are left to a later version, after evaluation.

## Interface

The interface is a "reading desk": the image occupies the main area on the left and can be zoomed; the right-hand column shows, in order, the user's article, A's first reading, B's response, and the follow-up input. A stage track at the top states plainly which step is current. Model output is grouped as "visible details / what the title suggests / interpretation" and "points from the literature / response / open questions", so that everything is not flattened into a single conclusion.

Visual direction: deep ink blue `#23343b` as the image mount, off-white `#f1f2ee` for the work area, mineral blue-green `#477575` to mark actionable state, copper brown `#a47b4e` to mark citations, and `#1c292e` for text. Body copy uses the system sans-serif stack; work titles fall back to a Chinese serif stack. Colour only aids recognition; every label keeps its wording.

## Technical structure

```text
Vue 3 / Vite frontend
  ├─ image and article input, upload validation, stage track
  ├─ A / B / A records and the researcher's follow-up
  └─ polling of run status
          │ HTTP JSON
          ▼
FastAPI application
  ├─ input validation and file storage
  ├─ fixed-flow controller: A → B → wait for follow-up → A
  ├─ model adapter: OpenAI-compatible Chat Completions API
  └─ SQLite: run state, user material, raw and validated model output
```

The frontend only displays and submits decisions; state transitions happen in the backend. Model keys are read from the server environment only. Every model response is parsed and validated; any article number B cites must belong to this run's user input. The image and the article text are never written to application logs.

## Data and endpoints

- `POST /api/runs`: accepts a title, an image, and at least one article; returns a `run_id`.
- `GET /api/runs/{run_id}`: returns the current state, each stage's validated output, and the article text and metadata the user supplied, so the work can be resumed after a reload.
- `GET /api/runs/{run_id}/image`: returns the image uploaded for this run.
- `POST /api/runs/{run_id}/followup`: while the run is waiting for the researcher, accepts one follow-up question and starts A's revision.
- `GET /api/health`: service check; exposes no keys.

States are `reading_a`, `reading_b`, `awaiting_question`, `revising_a`, `completed`, or `failed`. New runs get stable IDs. The first release is single-machine only; the service listens on the loopback address by default, and remote deployment requires authentication first. On restart, unfinished background jobs are marked failed and the stage records already saved are kept; the first release does not claim to resume automatically from an interruption.

## Acceptance

1. The application starts with no preloaded images or articles; the user can upload an image and an article and create a run.
2. A's request contains no article; B's request contains the article and the saved first reading from A; the revision request contains the researcher's follow-up.
3. B's source citations are validated, and the first reading is never overwritten by the revision.
4. After a page reload, completed stages are still viewable by run ID; a second follow-up is rejected.
5. When the model configuration is missing, an upload is malformed, model output is invalid, or a model request fails, the interface shows an understandable error and never disguises it as a successful result.

Implement against a fake model first to validate the flow, then run bounded tests against a real model to judge research quality. Flow tests cannot prove that art-historical judgements are sound; works familiar to the researcher must be checked item by item for image evidence, article provenance, and how the interpretation changes.
