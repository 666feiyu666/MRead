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

Two data profiles keep experiments and real work apart. **Development is the default.**

The `VAR=value command` form only works in POSIX shells (Git Bash, WSL, macOS, Linux).
In **Windows PowerShell** the variable must be set first in the same session:

```powershell
# 1. backend — dev profile, fake model, throwaway data under data/dev
cd backend
uv sync
$env:MREAD_PROVIDER = "fake"
uv run uvicorn app.main:app --port 8000

# 2. frontend, in a second shell
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173, proxies /api to :8000
```

Same thing in Git Bash / WSL / macOS / Linux:

```bash
cd backend && uv sync
MREAD_PROVIDER=fake uv run uvicorn app.main:app --port 8000
```

In `cmd.exe` use `set MREAD_PROVIDER=fake` on its own line before the same command, and
clear a variable again with `Remove-Item Env:MREAD_PROFILE` (PowerShell) or
`set MREAD_PROFILE=` (cmd).

### Daily use without retyping the variable

The backend reads a repository-root `.env` at startup, so the durable setting belongs
there — an explicitly set environment variable still wins over it:

```ini
# .env
MREAD_PROFILE=daily
```

Then everyday startup is just:

```powershell
cd backend
uv run uvicorn app.main:app --port 8000
```

and an experiment can override it for one shell with `$env:MREAD_PROFILE = "dev"`.

Or build the frontend once and let the backend serve it:

```powershell
cd frontend; npm run build
cd ..\backend; uv run uvicorn app.main:app --port 8000   # http://127.0.0.1:8000
```

`MREAD_PROVIDER=fake` runs a deterministic provider that never touches the network. It is
how the workflow, hand-offs, state machine, and validation are meant to be tested.

**uvicorn does not reload code by itself.** After changing anything under `backend/`, stop
the server and start it again, or run it with `--reload` while developing:

```powershell
uv run uvicorn app.main:app --port 8000 --reload
```

A stale backend is easy to spot: routes the UI offers (for example deleting a saved
reading) answer `405 Method Not Allowed`, and `GET /api/openapi.json` does not list them.

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
4. **Materials** — every upload in the case, in one place, with what it is and where it is
   used. Selecting a row shows the image at full size or the whole text, the stored
   metadata (id, mime, size, characters, upload time), and the steps that bind it. Title
   and provenance are editable; deleting removes the file, unbinds the material from every
   workflow step (bumping that workflow's version), and leaves past run records intact.

A failed model call, invalid output, or a reference to material a step never received
fails that step visibly; it is never turned into a research note.

## Saved readings

Every run is kept. A run is one row in `runs` (status, provider, workflow version, and the
exact case/workflow/profile snapshot it used), each step is a row in `step_records`
(what that step received, what it returned, and what validation refused), and each human
decision is a row in `decisions`. Nothing is overwritten when you run again.

The Read view lists the case's readings under **Run history**: newest first, numbered
from the first reading, with status, workflow version, completed steps, a one-line
excerpt, and the run id. Selecting one reopens that reading exactly as it was, including
its evidence highlights.

Readings are never edited. Each row can be deleted (two clicks), which removes only that
run, its step records, and its decisions — the case, its materials, and the workflows are
untouched, and the remaining readings keep their order and renumber. An older run left
waiting at a human step cannot be resumed; start a new run from Compose instead. Only the
newest run of a case can still accept its decision.

## What the runtime refuses

- **A step with nothing bound.** The run is refused before any model call, and the error
  names the step. Compose marks such a step `no material` and says what to do — a model
  asked to read nothing tends to answer from habit, which is exactly what this project
  exists to prevent.
- **An unsupported citation.** An evidence item that names material the step never
  received, an image region outside the frame or with a zero width/height, a passage past
  the end of the supplied text, or a reference to a claim that does not exist is dropped
  from the record and listed under **Rejected by validation** with the reason. The note,
  the claims that do resolve, and the open questions are kept — the researcher can see
  both what the model said and what the runtime refused. A malformed item (wrong type, a
  bare string) is rejected the same way, one item at a time.
- **Unreadable output.** A response with no usable `note`, or that is not a JSON object at
  all, fails the step outright, with a short readable reason.

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
