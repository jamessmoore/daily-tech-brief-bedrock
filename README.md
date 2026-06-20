# daily-tech-brief-bedrock

A nightly automated brief on DevOps/AI/MCP/cloud news, posted to Slack — built
entirely on AWS Bedrock, with no dependency on the Claude Code CLI.

This is a from-scratch rebuild of the [`daily-tech-brief`](https://github.com/jamessmoore/daily-tech-brief)
portfolio piece (which runs on the Claude Code CLI). Only the Slack-poster MCP
server is shared between the two — vendored here, called from a custom MCP
client instead of via the CLI's subagent/MCP plumbing.

## Architecture

```
EventBridge Scheduler (nightly cron, America/Phoenix)
        |
        v
Lambda (container image — Python 3.13 + Node 20 runtime)
        |
        1. Researcher: Bedrock Converse API tool-use loop, Claude Sonnet 4.6,
           with a custom web_search tool backed by Tavily. Iterates until it
           has enough material or hits a 6-call safety cap.
        |
        2. Synthesizer: second Bedrock Converse call, Claude Sonnet 4.6, no
           tools — turns the raw research into the final structured brief.
        |
        3. Delivery: a minimal stdio MCP client spawns the vendored
           slack-poster MCP server as a Node subprocess, performs the MCP
           initialize handshake, and calls post_to_slack with the brief.
        |
        v
Slack channel (#daily-brief by default)
```

Why a container image rather than a Lambda layer: the Lambda needs both a
Python runtime (orchestration) and a real Node.js runtime (to run the
vendored MCP server as a stdio subprocess). Two language runtimes talking
over stdio is fragile to wire up with layers; a container image gives full
control over both.

## Repository layout

```
terraform/        ECR repo, Lambda (container image), EventBridge Scheduler, IAM, Secrets Manager
app/
  handler.py        Lambda entrypoint
  bedrock_client.py Converse API wrapper + tool-use loop
  mcp_client.py     Minimal stdio MCP client
  tools/web_search.py   Tavily tool + Bedrock tool spec
  prompts/          System prompts for researcher + synthesizer
  slack_mcp_server/ Vendored slack-poster MCP server (Node, stdio transport)
  Dockerfile
.github/workflows/deploy.yml   Build/push image, terraform apply -- runs on push to main (and manually via workflow_dispatch)
```

## One-time setup

### 1. Enable Bedrock model access

Anthropic models on Bedrock require explicit model access approval per
account/region before they can be invoked.

1. Console: Bedrock → Model access → request access to Claude Sonnet 4.6 in
   your target region.
2. Find the exact model ID (or cross-region inference profile ID) once
   approved:
   ```
   aws bedrock list-foundation-models --region <region> \
     --query "modelSummaries[?contains(modelId,'sonnet')].modelId"
   # or, if using a cross-region inference profile:
   aws bedrock list-inference-profiles --region <region>
   ```
   Use that value for `bedrock_model_id` below.

### 2. Set up Tavily and Slack credentials

- Tavily: get an API key from tavily.com.
- Slack: the vendored `slack_mcp_server` needs a bot token with `chat:write`
  scope, invited to the target channel (`#daily-brief` by default).

### 3. Terraform state backend

Terraform state is **not local** — it lives in S3 so both your machine and
CI read/write the same state. The bucket can't be created by the same
config that uses it as a backend (chicken-and-egg), so bootstrap it once,
out of band:

```
aws s3api create-bucket --bucket <project>-tfstate-<account_id> \
  --region <region> --create-bucket-configuration LocationConstraint=<region>
aws s3api put-bucket-versioning --bucket <project>-tfstate-<account_id> \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket <project>-tfstate-<account_id> \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket <project>-tfstate-<account_id> \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Then point `terraform/main.tf`'s `backend "s3"` block at that bucket (bucket
name, key, region — see the existing block for the deployed instance's
values). Locking is native S3 conditional writes (`use_lockfile = true`),
which needs **Terraform 1.10+** — no DynamoDB lock table required.

### 4. Terraform variables and first deploy

```
cd terraform
terraform init
```

Create `terraform.tfvars` (gitignored, never committed):

```hcl
bedrock_model_id = "<value from step 1>"
tavily_api_key   = "<tavily key>"
slack_bot_token  = "<slack bot token>"
```

The Lambda's `image_uri` must point at an image that already exists in ECR,
so the very first deploy is two steps even with Terraform itself:

```
# 1. Create just the ECR repo
terraform apply -target=aws_ecr_repository.this

# 2. Build (note --provenance=false — see Dockerfile note below) and push
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account_id>.dkr.ecr.<region>.amazonaws.com
docker build --provenance=false -t <ecr_repo_url>:latest -f app/Dockerfile .
docker push <ecr_repo_url>:latest

# 3. Apply everything else
terraform apply
```

`--provenance=false` matters: modern `docker build` (buildx-backed) attaches
provenance/attestation manifests by default, producing a multi-manifest
image that Lambda's container runtime rejects outright
(`InvalidParameterValueException: ... media type ... is not supported`).

After this one-time bootstrap, `.github/workflows/deploy.yml` runs both
steps automatically on every push to `main`, and calls
`aws lambda update-function-code` so new image pushes actually take effect
(Terraform is told to ignore `image_uri` changes so it doesn't fight CI
over it).

### 5. GitHub Actions OIDC role

The workflow assumes an AWS IAM role via OIDC
(`secrets.AWS_DEPLOY_ROLE_ARN`) rather than long-lived access keys:

1. Create the OIDC provider once per AWS account (skip if it already exists
   — check with `aws iam list-open-id-connect-providers`):
   ```
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
   ```
2. Create a role trusting that provider, scoped to this repo and branch
   (not just the repo — `ref:refs/heads/main` specifically, so PR branches
   can't assume it):
   ```json
   {
     "Effect": "Allow",
     "Principal": { "Federated": "arn:aws:iam::<account_id>:oidc-provider/token.actions.githubusercontent.com" },
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {
       "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
       "StringLike": { "token.actions.githubusercontent.com:sub": "repo:<owner>/<repo>:ref:refs/heads/main" }
     }
   }
   ```
3. Attach a policy covering: ECR (push/pull + repo policy management),
   Lambda (create/update), the two Terraform-managed IAM roles (scoped to
   their exact ARNs, plus `iam:PassRole` on them), CloudWatch Logs, Secrets
   Manager (scoped to this project's secret name prefix), EventBridge
   Scheduler, and the Terraform state bucket from step 3. The same policy
   can be attached to whatever IAM user/role you deploy from locally — no
   need to maintain two separate permission sets.
4. Set repo secrets: `AWS_DEPLOY_ROLE_ARN` (the role's ARN),
   `BEDROCK_MODEL_ID`, `TAVILY_API_KEY`, `SLACK_BOT_TOKEN`.

## Testing before trusting the schedule

**Status:** confirmed working end-to-end in production — a manual invoke
has successfully run researcher → synthesizer → Slack delivery and posted
a real brief to `#daily-brief`. CI/CD is fully wired (push to `main` →
automated `terraform apply` + image build/push + Lambda update via GitHub
OIDC), and the nightly EventBridge schedule is enabled. The steps below are
still the right way to validate any further change before trusting it.

**Local (fastest feedback loop):**

```
docker build --provenance=false -t daily-tech-brief-bedrock -f app/Dockerfile .
docker run --rm \
  -e BEDROCK_MODEL_ID=<value> \
  -e AWS_REGION=<region> \
  -e TAVILY_API_KEY=<key> \
  -e SLACK_BOT_TOKEN=<token> \
  -e SLACK_CHANNEL=#daily-brief \
  -v ~/.aws:/root/.aws:ro \
  -p 9000:8080 \
  daily-tech-brief-bedrock

# in another terminal:
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```

(Skips Secrets Manager — env vars are read directly since `TAVILY_SECRET_ARN`/
`SLACK_SECRET_ARN` are unset, so `_load_secrets()` is a no-op.)

**Deployed, manual invoke:**

```
aws lambda invoke \
  --function-name daily-tech-brief-bedrock \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  --cli-read-timeout 620 \
  /tmp/out.json
cat /tmp/out.json
```

The Lambda timeout is 600s — the researcher's tool-use loop legitimately
needs that much headroom once conversation context grows past a few
iterations, so set `--cli-read-timeout` above it (the AWS CLI's own read
timeout is much shorter by default and will give up on you long before the
function actually finishes).

Check CloudWatch Logs (`/aws/lambda/daily-tech-brief-bedrock`) for the
researcher/synthesizer/delivery stage logs if anything fails — each stage
logs its own start/completion and exceptions before re-raising.

Once a manual invoke posts successfully to Slack, the EventBridge Scheduler
rule (nightly, `America/Phoenix` by default — see `schedule_expression` /
`schedule_timezone` in `terraform/variables.tf`) can be trusted to run
unattended.

## Contributing

- Please see the [contributors](CONTRIBUTOR.md) section for details.