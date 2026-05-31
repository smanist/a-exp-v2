# Kanban Output

Command:

```bash
a-exp-v2 kanban [project]
```

Output:

```text
reports/kanban/<project>.md
```

Existing files are overwritten.

The generator reads:

- `projects/<project>/TASKS.md`;
- `.a-exp/runs/*.json`;
- `projects/<project>/experiments/*/EXPERIMENT.md`;
- `projects/<project>/reports/**/*.md`;
- relevant workspace reports under `reports/`.

Output follows the old a-exp convention:

```markdown
## <project>-Tasks
- [x] **Progress**: <br>- <total> in total, <done> done
- [x] **Runs**: <br>- <task>: <status>, <ended_at>, <log_file>

## <project>-Results
- [x] **Experiment** <id>: <br>- <finding>
- [x] **Report** <id>: <br>- <finding>
```
