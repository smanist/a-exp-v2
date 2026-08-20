# Experiment Execution

Interactive and autonomous sessions may run multiple coherent experiments when
they advance the active study goal. Experiments must remain foreground children
of the Codex turn; detached launches and PID adoption are not supported in this
revision.

Before execution, consult `protocols/registry.yaml`. When a protocol applies,
use its playbook, schema, template, and checklist and record its id/version in
the experiment memory.

Record `producer: interactive` for Remote Project work and
`producer: autonomous` for runner work. Record enough durable information to
reproduce and interpret each experiment: question, context revision,
configuration, code revision, environment/GPU, commands, metrics,
artifacts, findings, caveats, and verification. Interactive work commits each
material experiment. During an autonomous run (`A_EXP_RUN_ID` is set), leave
the experiment changes in the worktree and declare them for the outer runner to
validate and commit. A session may then use those findings to choose another
experiment within the goal's autonomy envelope and remaining contingency caps.

Commit interactive positive, negative, or failed evidence whenever it changes
or justifies steering, a decision, the goal, or next direction. Disposable
probes that affect no decision may be omitted. The handoff references material
experiment IDs and artifacts but does not duplicate their full results.

If an experiment cannot safely finish within the session budget, stop it and
request an appropriate next state. Do not leave unmanaged work running.
