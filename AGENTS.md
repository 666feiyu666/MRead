# AGENTS.md

Working notes for anyone (human or agent) changing this repository.

## What this project is

MRead is an experimental multi-agent reading desk for images. A researcher uploads a
work of visual culture and an article of their own choosing; two agent roles take turns
reading it:

- **A** reads the image and its title only — never the article — and records visible
  details, associations the title invites, a preliminary interpretation, and open
  questions.
- **B** reads the user's article together with A's complete first reading, and responds
  with sourced points, support for or challenges to A's judgements, and questions back
  to the researcher.
- **The researcher** reads both records and writes one follow-up question.
- **A** then revises in the light of that question, stating what changed, what it kept,
  and what it still cannot settle.

The aim is not to produce a confident caption. It is to help researchers and viewers
read images *critically*: to see which claim rests on the picture, which on the title,
which on the literature, and where the disagreement is still live. Every design decision
should be judged against that goal.

## Language

The working language of this repository is **English**: documentation, code, comments,
commit messages, issue text, and review discussion. The design document and this file
were translated from Chinese for that reason; keep new writing in English.

The material under study may be Chinese (the sample work is the *Night Revels of Han
Xizai*), and user-facing copy will need to render Chinese text well — that is a content
and typography concern, not a reason to write the codebase in another language.

## Status

Design phase. `docs/design.md` is the single source of truth for scope, roles,
interface, data model, and acceptance criteria. No application code exists yet; read the
design document before proposing or writing any.

## Repository layout

```text
AGENTS.md          this file — how to work here
docs/design.md     MVP design: goal, roles, interface, endpoints, acceptance
.env               local model credentials (never committed)
```

Planned once implementation starts (see `docs/design.md`):

```text
frontend/          Vue 3 + Vite reading desk
backend/           FastAPI app: validation, fixed-flow controller, model adapter, SQLite
```

## Planned stack

- Frontend: Vue 3 with Vite; polling for run status; no workflow editor, no arbitrary
  tool execution.
- Backend: FastAPI, SQLite for run state and records, an OpenAI-compatible Chat
  Completions adapter for the model calls.
- Model credentials: server-side environment only (`DEEPSEEK_API_KEY`,
  `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL` live in `.env`). Never print keys, never send
  them to the frontend, never commit `.env`.
- The fixed sequence is A → B → researcher follow-up → A. One follow-up per run.

## Rules that must hold

These come from the design document; breaking one is a correctness bug, not a trade-off.

1. A's request carries the image and the title, and no article. B's request carries the
   article plus A's saved first reading, and no image. Each call uses its own context.
2. A's first reading is immutable once saved. Revision is a new record, and it must
   state the basis for each change.
3. B cites only material the user supplied in this run. No invented authors, page
   numbers, quotations, or sources; no web search; no added bibliography. Citations are
   validated against this run's input before they are shown.
4. Never infer what lies outside the frame. An uploaded file may be a detail of a larger
   work, so the system must not describe scenes it cannot see.
5. Keep evidence and interpretation visibly separate in both prompts and UI: visible
   details / what the title suggests / interpretation, and points from the literature /
   response / open questions.
6. Never write image bytes or article text to application logs.
7. Failures are shown as failures. Missing configuration, bad uploads, invalid model
   output, and request errors must produce an understandable error, never a
   success-shaped result.
8. Unresolved disagreement is a valid outcome and must be preserved, not smoothed away.

## Verification

No commands exist yet; record them here as soon as a build is set up. The policy the
design commits to:

- Validate flow against a **fake model** first — deterministic, no network.
- Then run bounded tests against the real model to judge research quality.
- Flow tests prove plumbing only. They do not prove art-historical reliability; that
  needs item-by-item checking on works a researcher knows, covering image evidence,
  article provenance, and how the interpretation changes.
- Scope checks to the change: reproduce the problem, run the narrowest relevant test,
  and review the diff before declaring work done.

## Git

- Remote: <https://github.com/666feiyu666/MRead> (branch `main`).
- `.env` is git-ignored; if credentials are ever committed, rotate them, they are
  compromised.
- Keep commits focused and describe the change in the imperative mood.
