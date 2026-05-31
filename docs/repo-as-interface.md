# Repo As Interface

An initialized repository contains the full operating state needed by future
agents. If a result, decision, artifact path, task, budget entry, or open
question is not written to repo files, later agents should treat it as unknown.

The normal work loop is:

1. Read `AGENTS.md`.
2. Read project memory under `projects/<project>/`.
3. Select the first runnable task in the selected project lane.
4. Triage execution mode: conventional, goal-mode, approval, or defer.
5. Execute only that task.
6. Close out into durable repo memory.
7. Inspect through `status`, `kanban`, or reports.

Runtime records under `.a-exp/` support status and provenance. They do not
replace durable project closeout.
