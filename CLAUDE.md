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

## Current status — read before assuming anything is live

As of this writing: the repo is scaffolded, nothing has been deployed to
AWS, and `main` branch protection / CI are not yet configured. The
near-term goal, in order, is:

1. Build CI checks (this repo's equivalent of `daily-tech-brief`'s `test`
   workflow — syntax/lint/validate, no AWS or Slack calls).
2. Configure `main` branch protection requiring that CI to pass before merge.
3. Only after both of those are solid: do a real first deploy (Bedrock model
   access enablement, `terraform apply`, manual Lambda invoke) per the
   README's testing section.

Do not run `terraform apply`, push an image, or otherwise touch real AWS
resources unless the user has explicitly asked for that in the current
request — per the master CLAUDE.md's "executing actions with care" guidance,
this is exactly the kind of hard-to-reverse, billed, shared-state action that
needs an explicit go-ahead each time, not a standing assumption.

## Required workflow — no direct commits to main

`main` will back the live nightly Lambda once deployed, and `push to main`
triggers `.github/workflows/deploy.yml` (build/push image, `terraform
apply`, `lambda update-function-code`). Unlike the old CLI-based repo, a
merge to `main` here **is** the deploy action, not just a no-op until some
separate host pulls new code. Treat every PR merge into `main` accordingly
once the deploy workflow is live.

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
  deploy.yml             # Build+push image, terraform apply, on push to main
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
