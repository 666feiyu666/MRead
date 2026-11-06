# MRead

A local reading desk for visual-culture research. You upload an image, its title, and
writing of your own; you define which agents take part, what each one receives, and where
a human decision sits in the exchange. The result is a traceable record of observations,
source claims, interpretations, revisions, and unresolved disagreement.

The design is in [`docs/design.md`](docs/design.md). A and B are a starting template, not
fixed roles: any step may use any profile, and a profile may be reused in later steps
without overwriting its earlier output.

## Requirements

- Python 3.11+ (3.13 is what this repository was built against) and [`uv`](https://docs.astral.sh/uv/)
- Node 20+ and npm
- A model key only if you want real model calls; the fake provider needs none

## Run it

Two data profiles keep experiments and real work apart. **Development is the default**:

```bash
# 1. backend — dev profile, fake model, throwaway data under data/dev
cd backend
uv sync
MREAD_PROVIDER=fake uv run uvicorn app.main:app --port 8000

# 2. frontend, in a second shell
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173, proxies /api to :8000
```

For the reading desk you actually keep cases in, start the backend with the daily
profile:

```bash
cd backend
MREAD_PROFILE=daily uv run uvicorn app.main:app --port 8000
```

Or build the frontend once and let the backend serve it:

```bash
cd frontend && npm run build
cd ../backend && MREAD_PROFILE=daily uv run uvicorn app.main:app --port 8000
# http://127.0.0.1:8000
```

`MREAD_PROVIDER=fake` runs a deterministic provider that never touches the network. It is
how the workflow, hand-offs, state machine, and validation are meant to be tested.

## Where data lives

| Profile | Directory | What belongs there |
| --- | --- | --- |
| `dev` (default) | `data/dev/` | Scratch cases, fake-model runs, UI experiments. Safe to delete at any time. |
| `daily` | `data/daily/` | The researcher's real cases, uploaded images, articles, and run records. |
| tests | temporary directory | Created by `backend/tests/conftest.py` and removed afterwards. |

Each profile has its own SQLite database and asset store (`data/<profile>/mread.db`,
`data/<profile>/assets/`), so the two never see each other's cases. The server prints
`MRead data: <path> (profile=<name>)` on startup, and the UI shows the profile in the top
bar (hover for the full path), so you can tell at a glance which one you are in.

`MREAD_DATA_DIR` overrides everything and is meant for tests and one-off experiments.

Both directories are git-ignored. Because `daily` lives inside the repository, back it up
before deleting or re-cloning the working copy — copy `data/daily/` somewhere else, or set
`MREAD_DATA_DIR` to a path outside the repository if you would rather keep it there.

## Configuration

Server-side environment only, usually a `.env` at the repository root (never committed):

| Variable | Meaning |
| --- | --- |
| `DEEPSEEK_API_KEY` | Model key. Never sent to the browser, never logged. |
| `DEEPSEEK_BASE_URL` | OpenAI-compatible base URL, default `https://api.deepseek.com`. |
| `DEEPSEEK_MODEL` | Default model when a profile names none. |
| `MREAD_PROVIDER` | `fake` or `openai`. Defaults to `openai` when a key exists, else `fake`. |
| `MREAD_TEXT_ONLY` | `1` stops image parts from being attached. Use it when the endpoint cannot read images. |
| `MREAD_PROFILE` | `dev` (default) or `daily`; picks the data directory. Any other name becomes `data/<name>`. |
| `MREAD_DATA_DIR` | Explicit data directory; overrides `MREAD_PROFILE` (tests use it). |
| `MREAD_SYNC_RUNS` | `1` runs steps inline instead of in a background thread (tests). |
| `MREAD_REQUEST_TIMEOUT` | Seconds before a model call is abandoned. |

**The DeepSeek chat completions endpoint accepts text only.** Start the backend with
`MREAD_TEXT_ONLY=1` when you use it, or image steps fail with the endpoint's own error
shown in the run record. The configured flow is still exercised end to end by the fake
provider; only real image judgement needs a vision-capable endpoint.

## Using it

1. **Prepare** — create a case, upload a PNG/JPEG/WebP image with a title, and add an
   article (PDF, TXT, MD, or pasted text) with a title and provenance. Nothing is
   preloaded.
2. **Compose** — a starting template appears once the case has materials. Edit agent
   profiles (role instructions, model, expected response), bind materials to each step,
   add or remove agent and human steps, and use **Preview inputs** to see exactly which
   material ids and prior steps each step will receive. **Run** snapshots the workflow.
3. **Read** — the image and the article sit beside the exchange. Selecting an evidence
   item highlights its image region or the cited character range in the article. A human
   step pauses the run: write one decision, and the remaining steps continue.

A failed model call, invalid output, or a reference to material a step never received
fails that step visibly; it is never turned into a research note.

## Tests

```bash
cd backend
uv run pytest -q
```

The suite drives the HTTP API with the fake provider and covers the acceptance criteria:
profile edits and bindings change the request, unbound material is absent from the call,
a human step pauses and resumes exactly once, earlier records are never overwritten,
invented asset ids, out-of-frame regions, out-of-range passages, dangling references, and
non-JSON output all fail visibly, and a reload restores the exchange.

Flow tests prove plumbing. They do not prove art-historical judgement; that needs
item-by-item checking on works a researcher knows.

## Limits of this version

- One machine, no authentication, no remote deployment.
- A single directed sequence: no cycles, no branches, no model-decided routing. Duplicate
  a step to ask for another pass.
- One human decision per human step; decisions are recorded once and cannot be revised.
- No OCR for scanned PDFs (paste the text), no web search, no automatic literature.
