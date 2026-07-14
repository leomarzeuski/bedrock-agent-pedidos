"""Wrapper HTTP (Lambda Function URL) que embrulha o agente Bedrock.

POST /  {mensagem, session?}  -> {resposta, session}   (exige header x-api-key)
GET  /                        -> {ok: true}            (health, sem auth, nao chama o agente)

Chama bedrock-agent-runtime.invoke_agent -- o mesmo caminho do invoke.py, so que
atras de uma URL HTTPS. Sem dependencias no zip: boto3 vem do runtime da Lambda e
e importado de forma preguicosa (o modulo importa so com stdlib; os testes injetam
um cliente falso em _CLIENT, sem rede nem inferencia)."""

import base64
import hmac
import json
import os
import time
import uuid

# Erros transientes do Bedrock que valem retentar (a propria API pede "try again").
TRANSIENTES = ("dependencyFailedException", "throttlingException", "modelTimeout")

_CLIENT = None  # cache do cliente boto3; os testes substituem por um fake


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        import boto3
        from botocore.config import Config

        # read_timeout alto: um turno pode encadear varias tools (CEP, cotacao, pedido).
        _CLIENT = boto3.client(
            "bedrock-agent-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(connect_timeout=10, read_timeout=120,
                          retries={"max_attempts": 2}),
        )
    return _CLIENT


def _resposta(status, corpo):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(corpo, ensure_ascii=False),
    }


def _invocar(agent_id, alias_id, session, texto):
    """Chama o agente, concatena os chunks do stream e retenta erros transientes."""
    client = _get_client()
    for tentativa in range(3):
        try:
            resp = client.invoke_agent(
                agentId=agent_id, agentAliasId=alias_id,
                sessionId=session, inputText=texto,
            )
            return "".join(
                ev["chunk"]["bytes"].decode()
                for ev in resp["completion"]
                if "chunk" in ev
            )
        except Exception as erro:
            transiente = any(t in str(erro) for t in TRANSIENTES)
            if tentativa < 2 and transiente:
                time.sleep(2 * (tentativa + 1))
                continue
            raise


def lambda_handler(event, context):
    metodo = event.get("requestContext", {}).get("http", {}).get("method", "")

    if metodo == "GET":
        return _resposta(200, {"ok": True})
    if metodo != "POST":
        return _resposta(405, {"erro": "metodo nao suportado; use POST"})

    esperada = os.environ.get("API_KEY", "")
    recebida = (event.get("headers") or {}).get("x-api-key", "")
    if not esperada or not hmac.compare_digest(recebida.encode(), esperada.encode()):
        return _resposta(401, {"erro": "unauthorized"})

    corpo_raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        corpo_raw = base64.b64decode(corpo_raw).decode()
    try:
        corpo = json.loads(corpo_raw)
        if not isinstance(corpo, dict):
            raise ValueError
    except (ValueError, TypeError):
        return _resposta(400, {"erro": 'body deve ser um JSON, ex.: {"mensagem": "oi"}'})

    mensagem = corpo.get("mensagem")
    if not isinstance(mensagem, str) or not mensagem.strip():
        return _resposta(400, {"erro": "campo 'mensagem' obrigatorio"})

    session = corpo.get("session") or f"api-{uuid.uuid4().hex[:8]}"

    try:
        texto = _invocar(
            os.environ["AGENT_ID"], os.environ["ALIAS_ID"], session, mensagem)
    except Exception as erro:
        print(f"erro ao invocar agente: {type(erro).__name__}: {erro}")
        return _resposta(500, {"erro": "falha ao consultar o agente"})

    return _resposta(200, {"resposta": texto, "session": session})
