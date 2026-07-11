import os
import sys
import uuid
import boto3

client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")

agent_id = os.environ.get("AGENT_ID", "1B0CRSOXZ3")
alias_id = os.environ.get("ALIAS_ID", "BBCPWBXHHZ")
session_id = sys.argv[2] if len(sys.argv) > 2 else f"cli-{uuid.uuid4().hex[:8]}"

response = client.invoke_agent(
    agentId=agent_id,
    agentAliasId=alias_id,
    sessionId=session_id,
    inputText=sys.argv[1],
)

for event in response["completion"]:
    if "chunk" in event:
        sys.stdout.write(event["chunk"]["bytes"].decode())

print(f"\n[session: {session_id}]")
