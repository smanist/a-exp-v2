# Scheduler Status SOP

An external scheduler should run `a-exp status --json` and invoke
`a-exp run-once` only when:

```text
health == "ok"
sessions.active == 0
work.runnable > 0
```

Keep the scheduler lease for the entire synchronous command. `run-once` returns
after the Codex turn and closeout finish. Exit `0` means no work or valid
closeout; exit `1` means execution, process-control, validation, or closeout
failure; exit `2` means invalid workspace/configuration.

On SIGINT or SIGTERM, forward the signal to the `a-exp` process group. `a-exp`
gives Codex up to 55 seconds to exit and then kills its process group, leaving
five seconds for failure closeout. At 60 seconds, force-kill the complete
descendant tree if needed and release the lease only after the child exits.

Per-study status exposes the current and last consumed context revisions. A
pending handoff means the committed revision has not yet produced a successful
completed session. Requested policy describes the handoff; the applied action
shows whether this machine started, resumed, replaced, or used resume fallback.
No scheduler or `a-cmd` behavior change is required for layout 3.
