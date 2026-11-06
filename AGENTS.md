# MRead

MRead is an experimental reading desk for visual-culture research. See
`docs/design.md` for the current product design.

## Working agreements

- Keep the project focused on user-supplied images, titles, and writing.
- Treat agent roles, material access, and hand-offs as configurable. A and B are
  examples, not fixed system roles.
- Keep observations, source claims, and interpretations distinguishable. Preserve
  earlier readings and unresolved disagreements.
- Before each development task, present a concrete plan for the user's review and
  wait for their approval before changing code.
- Keep the first implementation small. Validate workflow behavior with a fake
  model before bounded real-model trials.
- Keep model keys server-side and user material out of logs. Show failures clearly.
- Do not commit or push; leave changes for the user to review.
