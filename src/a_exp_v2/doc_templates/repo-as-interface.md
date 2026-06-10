# Repo As Interface

An initialized repository contains the full operating state needed by future
agents. If a result, decision, artifact path, task, budget entry, or open
question is not written to repo files, later agents should treat it as unknown.

The normal work loop is:

1. Read `AGENTS.md`.
2. Read project memory under `projects/<project>/`.
3. Select the first runnable task in the selected project lane.
4. Resolve its spec, if present, and follow hard `execution_mode`.
5. For legacy tasks only, triage execution mode: conventional, goal-mode,
   approval, or defer.
6. Execute only that selected task or goal.
7. Close out into durable repo memory.
8. Inspect through `status`, `kanban`, or reports.

Runtime records under `.a-exp/` support status and provenance. They do not
replace durable project closeout.
