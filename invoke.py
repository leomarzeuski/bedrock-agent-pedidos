import os
import sys
import time
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import EventStreamError

# read_timeout alto: um turno pode encadear varias tools (CEP, cotacao, pedido).
client = boto3.client(
    "bedrock-agent-runtime",
    region_name="us-east-1",
    config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 2}),
)

agent_id = os.environ.get("AGENT_ID", "1B0CRSOXZ3")
alias_id = os.environ.get("ALIAS_ID", "YLMKONTXKO")
session_id = sys.argv[2] if len(sys.argv) > 2 else f"cli-{uuid.uuid4().hex[:8]}"

# Erros transientes do Bedrock que valem retentar (a propria API pede "try again").
TRANSIENTES = ("dependencyFailedException", "throttlingException", "modelTimeout")


def responder(texto):
    resp = client.invoke_agent(
        agentId=agent_id, agentAliasId=alias_id, sessionId=session_id, inputText=texto
    )
    partes = [
        event["chunk"]["bytes"].decode()
        for event in resp["completion"]
        if "chunk" in event
    ]
    return "".join(partes)


texto = sys.argv[1]
for tentativa in range(3):
    try:
        sys.stdout.write(responder(texto))
        break
    except EventStreamError as erro:
        if tentativa < 2 and any(t in str(erro) for t in TRANSIENTES):
            time.sleep(2 * (tentativa + 1))
            continue
        raise

print(f"\n[session: {session_id}]")
