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

`.github/workflows/deploy.yml` is still `workflow_dispatch`-only (manual) —
it has *not* been switched to trigger on push to `main` yet. Deploys
(`terraform apply`, image rebuild/push, `aws lambda update-function-code`)
are still done manually per the README's deploy steps. The EventBridge
Scheduler resource exists and is `ENABLED`, so once "Bedrock model access,
secrets, OIDC role" trust is established this could actually fire nightly —
double check `aws scheduler get-schedule` state before assuming it's
dormant.

Bugs found and fixed only by running the real pipeline against live AWS
(mocked unit tests didn't catch any of these — see git log on `app/` for
the individual fixes): Bedrock IAM permissions for cross-region inference
profiles, ECR image manifest format (buildx attestations break Lambda),
ECR repository policy for Lambda's pull access, vendored file permissions
(600 → unreadable by Lambda's non-root user), Bedrock client hanging
indefinitely with no timeout/retry config, `toolResult` `json` field
rejecting list results, growing message-history payload size stalling
Converse calls past iteration 3-4, and the forced-final-answer fallback
dropping required `toolConfig`. Useful context if something in this area
breaks again — check whether it's a recurrence of one of these before
re-diagnosing from scratch.

Still treat `terraform apply`, image pushes, or other real AWS-touching
actions as needing an explicit go-ahead in the current request, not a
standing assumption — per the master CLAUDE.md's "executing actions with
care" guidance. The bar now is "don't redeploy/reinvoke without being
asked," not "deployment has never been attempted."

## Required workflow — no direct commits to main

`main` will back the live nightly Lambda once deployed. `deploy.yml`
(build/push image, `terraform apply`, `lambda update-function-code`) is
currently `workflow_dispatch`-only (manual) — deliberately not wired to
`push: branches: [main]` yet, so merges can't accidentally trigger a real AWS
deploy before Bedrock access, secrets, and the OIDC role are actually set up
and a manual deploy has been verified. Once that's done and `deploy.yml` is
switched to trigger on push, a merge to `main` **becomes** the deploy
action — update this note when that switch happens.

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
terraform/               # ECR, Lambda (container image), EventBridge Scheduler, IAM, Secrets Manager
tests/                   # pytest unit tests for app/ (mocked boto3, fake stdio MCP server -- no AWS/Slack calls)
.github/workflows/
  test.yml               # CI gate: lint/type-check/unit tests/terraform validate, on every PR to main
  deploy.yml             # Build+push image, terraform apply -- manual (workflow_dispatch) for now
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
