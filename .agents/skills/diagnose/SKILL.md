---
name: diagnose
description: Interpret unexpected or confusing empirical results.
---

# Diagnose

Use this skill when results need interpretation rather than claim validation.

Read the result set first. Then:

1. Characterize the distribution of errors/results.
2. Break results down by relevant condition.
3. Generate root-cause hypotheses.
4. Classify causes by layer:
   - model/capability;
   - workflow;
   - interface;
   - methodology;
   - human/ground truth.
5. Assess construct, statistical, external, and ground-truth validity.
6. Recommend concrete next steps.

Distinguish data interpretation from agent failure analysis. If the issue is
whether written conclusions are supported, use `review` instead.

Record durable diagnoses under `projects/<project>/` or `reports/`.

## Git Closeout

After writing repo changes, run `git status --short`, commit the intended
changes, and leave the workspace clean except for intentionally ignored files.
