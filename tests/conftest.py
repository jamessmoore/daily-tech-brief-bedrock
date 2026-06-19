import os

# handler.py reads BEDROCK_MODEL_ID at import time (fails fast if unset in a
# real deploy). Tests need a value present before `import handler` happens,
# regardless of test collection order, so set it here rather than in a
# per-test fixture.
os.environ.setdefault("BEDROCK_MODEL_ID", "fake-model-id-for-tests")
os.environ.setdefault("AWS_REGION", "us-east-1")
