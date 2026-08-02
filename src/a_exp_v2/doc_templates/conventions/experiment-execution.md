# Experiment Execution

Autonomous sessions may run multiple coherent experiments when they advance the
active study goal. Experiments must remain foreground children of the Codex
turn; detached launches and PID adoption are not supported in this revision.

Before execution, consult `protocols/registry.yaml`. When a protocol applies,
use its playbook, schema, template, and checklist and record its id/version in
the experiment memory.

Record enough durable information to reproduce and interpret each experiment:
question, configuration, code revision, environment, commands, metrics,
artifacts, findings, caveats, and verification. Commit after each material
experiment. A session may then use those findings to choose another experiment
within the goal's autonomy envelope.

If an experiment cannot safely finish within the session budget, stop it and
request an appropriate next state. Do not leave unmanaged work running.
