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

On SIGINT or SIGTERM, forward the signal to the `a-exp` process group, wait up
to 60 seconds, force-kill if needed, and release the lease only after exit.
