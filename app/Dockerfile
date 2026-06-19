# Stage 1: install the vendored slack-poster MCP server's node_modules in a
# real Node environment (faster + cleaner than installing npm into the Lambda
# base image just to run `npm ci`).
FROM node:20-slim AS slack_mcp_build
WORKDIR /build
COPY app/slack_mcp_server/package.json app/slack_mcp_server/package-lock.json ./
RUN npm ci --omit=dev

# Stage 2: Lambda runtime image. Needs both Python (orchestration) and a real
# Node 20 runtime (to exec the vendored MCP server as a stdio subprocess) —
# that's why this is a container image rather than a Lambda layer.
FROM public.ecr.aws/lambda/python:3.13

# AL2023 base image; nodejs20 is available via dnf.
RUN dnf install -y nodejs20 && dnf clean all

COPY app/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app/ ${LAMBDA_TASK_ROOT}/
COPY --from=slack_mcp_build /build/node_modules ${LAMBDA_TASK_ROOT}/slack_mcp_server/node_modules

CMD ["handler.lambda_handler"]
