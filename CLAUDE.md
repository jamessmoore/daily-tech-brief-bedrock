# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

A nightly Slack brief on DevOps/AI/MCP/cloud news, built entirely on AWS
Bedrock: EventBridge Scheduler triggers a Lambda (container image, Python
3.13 + Node 20) that runs a Bedrock Converse API researcher step (tool-use
loop with a Tavily `web_search` tool), a synthesizer step (no tools), then
delivers the result to Slack via a vendored MCP server
(`app/slack_mcp_server/`) called from a custom stdio MCP client
(`app/mcp_client.py`). No Claude Code CLI involvement at runtime — this is a
from-scratch rebuild of the sibling repo `daily-tech-brief` (which runs on
the CLI), sharing only the Slack-poster MCP server's source. See `README.md`
for full architecture and one-time setup (Bedrock model access, Terraform,
OIDC). This is also a public portfolio piece (webtechhq.com/portfolio), so
README and commit history should stay client-presentable.

## Current status — read before assuming anything is stale

As of this writing: CI (`test` workflow) and `main` branch protection are
both live, and a real deploy exists in AWS account `293528978619`
(us-west-2) — ECR repo, Lambda (container image), IAM roles, Secrets
Manager entries, EventBridge Scheduler. A manual Lambda invoke has
successfully run the full pipeline end-to-end and posted a real brief to
the `#daily-brief` Slack channel (user-confirmed).

Full CI/CD is live: `.github/workflows/deploy.yml` triggers on push to
`main` (and via manual `workflow_dispatch`), assumes AWS via GitHub OIDC
(role `daily-tech-brief-bedrock-github-deploy`, trust-scoped to
`repo:jamessmoore/daily-tech-brief-bedrock:ref:refs/heads/main` — no
long-lived AWS keys in GitHub), and has now run an automated `terraform
apply` + image build/push + `lambda update-function-code` end to end
**via an actual push-to-`main` merge** (PR #15, run completed in 1m32s) —
not just a manual `workflow_dispatch` test. The "a merge to `main` is the
deploy action" claim below is empirically confirmed, not aspirational.
Terraform state lives in S3
(`daily-tech-brief-bedrock-tfstate-293528978619`, native locking via
`use_lockfile`, requires Terraform 1.10+) — both local CLI runs and CI read
the same state, so **a merge to `main` now genuinely is the deploy
action**. The EventBridge Scheduler is `ENABLED` and will fire nightly
unattended — don't assume it's dormant; check `aws scheduler get-schedule`
if in doubt.

The local deploy user (`flintstone`) and the CI OIDC role share one IAM
managed policy (`daily-tech-brief-bedrock-deploy`) so permissions don't
drift between manual and automated deploys. If a deploy fails on a
permissions error, that policy is almost certainly what needs a new version
— it's been bumped ~6 times already as real deploy/runtime gaps surfaced
(see policy history if accessible, or just reason from the error).

Bugs found and fixed only by running the real pipeline against live AWS
(mocked unit tests didn't catch any of these — see git log on `app/` for
the individual fixes): Bedrock IAM permissions for cross-region inference
profiles, ECR image manifest format (buildx attestations break Lambda),
ECR repository policy for Lambda's pull access, vendored file permissions
(600 → unreadable by Lambda's non-root user), Bedrock client hanging
indefinitely with no timeout/retry config, `toolResult` `json` field
rejecting list results, growing message-history payload size stalling
Converse calls past iteration 3-4, the forced-final-answer fallback
dropping required `toolConfig`, hardcoded wrong region in `deploy.yml`, and
missing `--provenance=false` on the CI Docker build (same image-manifest
bug as above, just in the automated path). Useful context if something in
this area breaks again — check whether it's a recurrence of one of these
before re-diagnosing from scratch.

Given CI/CD is now real and automatic, **merging to `main` deploys to
production** — review PRs touching `app/`, `terraform/`, or `Dockerfile`
accordingly. Still treat any *manual* `terraform apply`, direct image push,
or `aws lambda invoke` outside the normal PR flow as needing an explicit
go-ahead in the current request, per the master CLAUDE.md's "executing
actions with care" guidance.

## Required workflow — no direct commits to main

`main` backs the live nightly Lambda. Every merge to `main` triggers
`deploy.yml` (build/push image, `terraform apply`, `lambda
update-function-code`) via GitHub OIDC — a merge **is** the deploy action,
not a no-op. Treat every PR into `main` accordingly.

1. Create a new branch off `main` for the change (e.g. `git checkout -b fix/short-description`).
2. Commit changes to that branch.
3. Push the branch and open a pull request targeting `main` (`gh pr create`).
4. Wait for CI (the `test` / `test` status check — see `.github/workflows/test.yml`) to pass on the PR.
5. Merge the PR into `main` only after CI passes.
6. After a successful merge, delete the local feature branch (`git branch -d <branch>`) and run `git fetch --prune`.

Never commit directly to `main` and never push directly to `main`. Once the
"Protect main" ruleset is configured (item 2 above), this is enforced by
GitHub, not just convention — no bypass actors, applies even to repo admins.

## Local verification before opening/updating a PR

This mirrors `.github/workflows/test.yml` exactly — if these pass locally,
the `test` status check will pass. None of it touches AWS, Bedrock, Tavily,
or Slack; it's a config/logic-correctness gate, not an integration test.

```bash
# Slack MCP server (vendored, untouched logic — just confirm it still parses)
cd app/slack_mcp_server && npm install && node --check index.js && cd ../..

# Python — use a venv (uv venv .venv && uv pip install -p .venv -r app/requirements.txt -r requirements-dev.txt)
ruff check app tests
mypy app
pytest

# Terraform
cd terraform && terraform fmt -check -recursive . && terraform init -backend=false && terraform validate && cd ..
```

Keep this section, `pyproject.toml` (ruff/mypy/pytest config), and
`.github/workflows/test.yml` in sync if any of these checks change.

## Project structure

```
app/
  handler.py            # Lambda entrypoint: secrets -> researcher -> synthesizer -> Slack
  bedrock_client.py      # Converse API wrapper + tool-use loop
  mcp_client.py          # Minimal stdio MCP client (JSON-RPC over stdio)
  tools/web_search.py    # Tavily tool implementation + Bedrock tool spec
  prompts/               # researcher_system.md, synthesizer_system.md
  slack_mcp_server/      # Vendored MCP server (post_to_slack, post_file_to_slack) — source only, node_modules built in Docker
  Dockerfile             # Lambda Python 3.13 base + Node 20
  requirements.txt
terraform/               # ECR, Lambda (container image), EventBridge Scheduler, IAM, Secrets Manager; state in S3 (see main.tf backend block)
tests/                   # pytest unit tests for app/ (mocked boto3, fake stdio MCP server -- no AWS/Slack calls)
.github/workflows/
  test.yml               # CI gate: lint/type-check/unit tests/terraform validate, on every PR to main
  deploy.yml             # Build+push image, terraform apply -- runs on push to main via GitHub OIDC (and manually via workflow_dispatch)
pyproject.toml           # ruff/mypy/pytest config
requirements-dev.txt     # pytest, ruff, mypy
.env.example
```

## Secrets

- `.env`, `terraform/*.tfvars`, `terraform/*.auto.tfvars` are gitignored —
  never commit them, print their contents, or paste real values into
  commits, PRs, or commit messages.
- `.env.example` documents required variables with placeholders only —
  update it when adding new variables, never with real values.
- Real credentials (`TAVILY_API_KEY`, `SLACK_BOT_TOKEN`, `BEDROCK_MODEL_ID`)
  live in AWS Secrets Manager / GitHub Actions secrets, not in this repo.
- `app/slack_mcp_server/node_modules/` and Terraform state/lock files are
  gitignored.

## Commit messages

Short, imperative, capitalized summary line. No conventional-commit prefixes
(`feat:`, `fix:`, etc.) — matches the sibling `daily-tech-brief` repo's style.

## Notes

- This repo is referenced from the user's global CLAUDE.md as a featured
  portfolio project — keep README and commit history client-presentable.
- `app/slack_mcp_server/index.js` is vendored from `daily-tech-brief`'s
  `mcp-servers/slack-poster/index.js`. Don't diverge its logic without a
  reason — if it needs a fix, consider whether the fix belongs upstream in
  the original repo too.
- Lambda image build is multi-stage (`node:20-slim` for `npm ci`, then the
  AL2023-based `public.ecr.aws/lambda/python:3.13` image with `nodejs20` via
  `dnf`) — both runtimes need to coexist in the same container because the
  MCP server runs as a subprocess over stdio inside the same invocation.
- Terraform's `aws_lambda_function.this` has `lifecycle { ignore_changes =
  [image_uri] }` because CI updates the running image via `aws lambda
  update-function-code` directly — don't remove that without also changing
  how `deploy.yml` ships new images, or applies will start fighting CI.
