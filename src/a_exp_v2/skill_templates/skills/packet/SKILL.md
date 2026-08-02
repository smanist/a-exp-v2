---
name: packet
description: Create implementation handoff packets from a-exp-v2 studies.
---

# Packet

Use this skill to transfer a separately scoped implementation from study memory
to an `a-dev` workflow or external package.

Read the target package instructions and relevant study `README.md`, `GOAL.md`,
plans, decisions, sessions, experiments, protocols, reports, modules, and
artifact manifests. Write an implementation-ready Markdown packet under
`reports/packet/`.

Include purpose, computational contract, evidence and verified behavior,
prototype/artifact paths, target integration points, dependencies, edge cases,
test plan, example usage, and risks. A packet is an explicit boundary for work
whose scope should be owned elsewhere; it is not an internal scheduler unit.

Commit the packet and leave the checkout clean.
