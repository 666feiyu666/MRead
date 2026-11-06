# MRead: A Visual-Culture Multi-Agent Reading Desk

## Purpose

MRead helps a researcher examine how an image, its title, and user-supplied writing shape one another. The researcher uploads the materials, defines the participating agents, decides what each one receives, and inspects the resulting exchange. The useful result is a traceable record of observations, sources, interpretations, revisions, and unresolved questions.

The supplied detail of *The Night Revels of Han Xizai* is a case for trying a workflow. It is not built-in content. A user may upload a full work or a crop; an agent must identify the limits of the visible frame when making a visual claim.

## The correction to the first design

**A and B are agent configurations, not permanent product roles.** “A reads the image and title; B reads articles and responds to A” is one workflow template. A researcher may change either agent's instructions, change which uploaded materials a step receives, reuse an agent in a later step, add another agent, or choose a different hand-off. The runtime must not infer permissions or sequence from the letters A and B.

The product remains specific to visual-culture research. Its configurable inputs are images, titles, articles, image regions, source passages, and prior agent records. It does not need a general-purpose coding agent platform.

## What to take from ChatDev 2.0

[ChatDev 2.0](https://github.com/OpenBMB/ChatDev) separates [agent-node configuration](https://github.com/OpenBMB/ChatDev/blob/main/docs/user_guide/en/nodes/agent.md) from a [graph of nodes and edges](https://github.com/OpenBMB/ChatDev/blob/main/docs/user_guide/en/workflow_authoring.md). Its [visual tutorial](https://github.com/OpenBMB/ChatDev/blob/main/frontend/public/tutorial-en.md) shows how messages cross edges, how a node's context is scoped, and how a human node can affect execution.

MRead should adopt four mechanisms:

1. **Editable agent profiles.** A profile states a role, research task, model, and output expectations. A model can serve several agents; each invocation still has its own context.
2. **Explicit workflow steps.** A step invokes a profile with a selected bundle of materials and prior messages. Reusing profile A in two steps does not create a new role or overwrite its earlier output.
3. **Visible hand-offs.** An edge says which step follows and which outputs it passes. An agent never gains access to every uploaded article merely because it participates in the run.
4. **Human participation and run records.** The researcher can pause, inspect the actual hand-off, ask a question, and continue. The interface retains both earlier and later readings.

The graph editor is a means of composing a reading procedure. The main research view remains the image and its evidence, rather than a generic automation canvas.

## Core concepts

| Concept | Meaning in MRead | Owner |
| --- | --- | --- |
| Case | A user-uploaded image, title, and optional articles or notes, each with a stable ID and provenance supplied by the user | Researcher |
| Agent profile | Editable name, role instructions, model selection, and expected response format | Researcher |
| Workflow step | A named invocation of one profile with explicit material and message bindings | Workflow |
| Edge | A directed hand-off of selected outputs from one step to another | Workflow |
| Human step | A pause that presents prior outputs and accepts a question, selection, or decision | Researcher |
| Run | An immutable snapshot of the case, profile versions, and workflow version, plus step records and status | Runtime |
| Evidence reference | A link from a claim to an uploaded image region, article passage, title, or earlier claim | Runtime-validated record |

Profile instructions describe *how* an agent works. Step bindings determine *what it can see in this invocation*. Workflow edges determine *what it receives from other steps*. These three controls are shown separately in the UI.

An agent profile may be used more than once in one workflow. Each invocation has a new step ID and output record. A selected earlier message may be passed forward; there is no implicit shared conversation or unrestricted global memory.

## Example template: image, literature, return

The following is an editable starting template for the supplied *Night Revels* case:

```text
User uploads image + title + article(s)
              │
              ▼
Step 1 · Agent A: image + title
              │ pass A's first reading
              ▼
Step 2 · Agent B: selected article(s) + A's first reading
              │ pass B's response and selected A claims
              ▼
Step 3 · Researcher: inspect and ask a question
              │ pass the question and selected prior records
              ▼
Step 4 · Agent A again: image + title + selected records + question
              │
              ▼
End · preserve all four step records
```

The suggested A profile distinguishes visible detail, title-led association, and interpretation. The suggested B profile reads the supplied articles, responds to A, and cites those articles. These are defaults in the template, not restrictions on all agents named A or B. For example, the researcher can give B the image, remove the title from A's first step, add a third agent to question a source, or end the workflow after B.

The first version should allow editing profiles, step inputs, order, and hand-offs. It supports a directed sequence of agent and human steps; the same profile may appear in several steps. Automatic cycles, model-decided routing, and parallel branches can follow once this basic exchange is evaluated. A researcher can duplicate a step to request another pass without an automatic loop.

## Evidence and output

Every step produces a readable note and, where claims are made, structured evidence items:

- **Observation:** what is visible, with an optional region on the uploaded image.
- **Source report:** what a user-supplied article says, linked to that article and a passage when available.
- **Interpretation:** a claim that explains or connects material, linked to the observations or source reports it uses.
- **Question or disagreement:** what remains open and which earlier claim it addresses.

These are claim types, not agent types. Any agent can produce them if its task calls for them. A model response is treated as untrusted: the backend validates structure, referenced asset IDs, and passage or region bounds. A valid reference does not prove that the source supports the claim; the researcher must be able to inspect the underlying material.

Original source wording remains visible when quoted. The interface labels paraphrases and translations so neither is presented as a quotation. Later interpretations and revisions are appended; earlier records remain available.

## Interface

The interface has three connected views:

1. **Prepare:** upload a PNG, JPEG, or WebP image; enter its title; upload text-extractable PDF, TXT, or MD articles or paste text. Give each article a title and optional bibliographic information. A scanned PDF without extractable text prompts the user to supply text.
2. **Compose:** a compact canvas inspired by ChatDev's graph UI. Agent cards show profile name and model; selecting a card opens its role instructions and the exact materials bound to that step. An edge inspector shows which outputs it passes. The researcher can add or reuse a profile and insert a human step. A preview lists exactly what each model call will receive.
3. **Read:** a zoomable image and article viewer sit beside a chronological exchange. Selecting an evidence item highlights its image region or source passage. The current workflow step is visible; a human step presents a clear question or decision input. The researcher can compare an agent's first and later readings without losing either.

The graph is visible enough to explain the exchange but does not replace the reading surface. ChatDev 2.0 uses Vue 3, Vite, and Vue Flow in its [frontend](https://github.com/OpenBMB/ChatDev/blob/main/frontend/package.json); this is a reasonable implementation reference for the compose view. The rest of the UI should be designed around visual comparison and source inspection.

Visual direction: deep ink blue `#23343b` for the image mount, off-white `#f1f2ee` for the reading surface, mineral blue-green `#477575` for active controls, copper brown `#a47b4e` for references, and `#1c292e` for text. Labels always carry meaning independently of colour.

## Runtime and storage

```text
Vue 3 / Vite UI
  ├─ case materials and source viewer
  ├─ agent-profile and workflow-step editor
  └─ run timeline, evidence links, human decisions
             │
             ▼
FastAPI application
  ├─ upload and source validation
  ├─ graph validation and deterministic step scheduler
  ├─ provider adapters and response validation
  └─ SQLite + local asset store for profiles, workflow versions, runs, and evidence
```

The UI submits a workflow definition; the backend validates it before any model call. Each run snapshots the exact profile, model, asset, and edge configuration used. The scheduler assembles each step's payload from its bindings and inbound edges; profile names have no special behavior. A human step pauses the run, and only an explicit decision resumes it. Step and run states are saved before the UI reports completion.

The first version runs locally on one machine. Model keys stay server-side. Uploaded articles and model output are data, not instructions to change permissions or workflow policy. Image bytes, article text, and keys are excluded from application logs. A failed model call or invalid response yields a visible failed step; it is not converted into a successful research note.

Useful API operations are `create/update agent profile`, `create/update workflow`, `upload case material`, `start run`, `inspect run`, and `submit human decision`. The exact HTTP routes can be fixed during implementation; no endpoint should be named for A or B.

## MVP boundary

The first implementation should include user-supplied materials, editable agent profiles, an editable sequence of steps and hand-offs, one or more human pauses, model selection per profile, a persistent run timeline, and evidence links back to the supplied image or article. It should work when two profiles share a model and when they use different configured models, provided the assigned model supports each step's inputs.

The first implementation does not require automatic article retrieval, arbitrary shell or code tools, a general-purpose marketplace of agent roles, unrestricted graph cycles, multi-user collaboration, or remote deployment. These features do not help establish whether the reading exchange is useful.

## Acceptance

1. No image or article is preloaded. A researcher uploads materials and can edit the default A/B template before running it.
2. Changing A's or B's profile instructions changes the corresponding model request; changing a step binding changes which materials it receives. A label alone never determines access.
3. The researcher can reuse A in a later step, add another agent profile, or end after B without changing backend code.
4. Before each call, the run record shows the exact material IDs and prior step IDs included. A fake-provider test proves that an unbound article or image is absent from that call.
5. A human step pauses and resumes once with the recorded decision. Earlier outputs remain immutable; duplicate or stale decisions are rejected.
6. Every evidence reference resolves to an uploaded asset or earlier record. Unsupported interpretations can remain visible as unresolved claims; the system does not force consensus.
7. A page reload restores the case, workflow version, step statuses, and exchange. Invalid input, provider failure, and invalid model output produce explicit failure states.

Implementation should first verify routing and state with a fake provider. A bounded study with real models and researcher-supplied works should then assess whether the exchange makes visual evidence, article provenance, and changes of interpretation easier to examine.
