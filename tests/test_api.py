"""Testes da wrapper HTTP (Lambda Function URL) que embrulha o agente Bedrock.

Offline: injeta um cliente falso no lugar do boto3, nenhuma chamada real de rede
ou inferencia. O modulo da API vive em api/app.py (nome 'app' para nao colidir com
lambda/handler.py, que a conftest ja poe no sys.path)."""

import base64 as b64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import app  # noqa: E402


class FakeClient:
    """Finge o bedrock-agent-runtime: invoke_agent devolve chunks fixos e
    registra os kwargs recebidos. Pode levantar excecoes antes de responder,
    para exercitar o retry."""

    def __init__(self, chunks=(b"Ola", b" mundo"), erros=()):
        self.chunks = list(chunks)
        self.erros = list(erros)
        self.chamadas = []

    def invoke_agent(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erros:
            raise self.erros.pop(0)
        return {"completion": [{"chunk": {"bytes": b}} for b in self.chunks]}


def _evento(metodo="POST", headers=None, body=None, base64_encoded=False):
    ev = {
        "requestContext": {"http": {"method": metodo}},
        "headers": {k.lower(): v for k, v in (headers or {}).items()},
        "isBase64Encoded": base64_encoded,
    }
    if body is not None:
        ev["body"] = body if isinstance(body, str) else json.dumps(body)
    return ev


def _setup(monkeypatch, fake=None):
    fake = fake or FakeClient()
    monkeypatch.setenv("API_KEY", "segredo123")
    monkeypatch.setenv("AGENT_ID", "AG123")
    monkeypatch.setenv("ALIAS_ID", "AL123")
    monkeypatch.setattr(app, "_CLIENT", fake)
    monkeypatch.setattr(app.time, "sleep", lambda s: None)  # nao espera no retry
    return fake


def _corpo(resp):
    return json.loads(resp["body"])


def _auth(body):
    return _evento("POST", headers={"x-api-key": "segredo123"}, body=body)


def test_health_get_nao_exige_chave_nem_chama_agente(monkeypatch):
    fake = _setup(monkeypatch)
    resp = app.lambda_handler(_evento("GET"), None)
    assert resp["statusCode"] == 200
    assert _corpo(resp) == {"ok": True}
    assert fake.chamadas == []


def test_post_sem_chave_401(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(_evento("POST", body={"mensagem": "oi"}), None)
    assert resp["statusCode"] == 401


def test_post_chave_errada_401(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(
        _evento("POST", headers={"x-api-key": "errada"}, body={"mensagem": "oi"}), None)
    assert resp["statusCode"] == 401


def test_post_body_nao_json_400(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(_auth("isso nao e json"), None)
    assert resp["statusCode"] == 400


def test_post_sem_mensagem_400(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(_auth({"session": "x"}), None)
    assert resp["statusCode"] == 400


def test_post_mensagem_vazia_400(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(_auth({"mensagem": "   "}), None)
    assert resp["statusCode"] == 400


def test_metodo_nao_suportado_405(monkeypatch):
    _setup(monkeypatch)
    resp = app.lambda_handler(_evento("DELETE"), None)
    assert resp["statusCode"] == 405


def test_post_ok_concatena_resposta_e_gera_session(monkeypatch):
    fake = _setup(monkeypatch, FakeClient(chunks=(b"Ola", b", ", b"pedido!")))
    resp = app.lambda_handler(_auth({"mensagem": "oi"}), None)
    assert resp["statusCode"] == 200
    corpo = _corpo(resp)
    assert corpo["resposta"] == "Ola, pedido!"
    assert corpo["session"].startswith("api-")
    assert fake.chamadas[0]["inputText"] == "oi"
    assert fake.chamadas[0]["sessionId"] == corpo["session"]
    assert fake.chamadas[0]["agentId"] == "AG123"
    assert fake.chamadas[0]["agentAliasId"] == "AL123"


def test_post_reusa_session_informada(monkeypatch):
    fake = _setup(monkeypatch)
    resp = app.lambda_handler(_auth({"mensagem": "oi", "session": "api-abc123"}), None)
    corpo = _corpo(resp)
    assert corpo["session"] == "api-abc123"
    assert fake.chamadas[0]["sessionId"] == "api-abc123"


def test_body_base64_decodificado(monkeypatch):
    fake = _setup(monkeypatch)
    body_b64 = b64.b64encode(json.dumps({"mensagem": "oi"}).encode()).decode()
    resp = app.lambda_handler(
        _evento("POST", headers={"x-api-key": "segredo123"}, body=body_b64,
                base64_encoded=True), None)
    assert resp["statusCode"] == 200
    assert fake.chamadas[0]["inputText"] == "oi"


def test_retry_em_erro_transiente(monkeypatch):
    erro = RuntimeError("dependencyFailedException: try again")
    fake = _setup(monkeypatch, FakeClient(chunks=(b"ok",), erros=[erro]))
    resp = app.lambda_handler(_auth({"mensagem": "oi"}), None)
    assert resp["statusCode"] == 200
    assert _corpo(resp)["resposta"] == "ok"
    assert len(fake.chamadas) == 2  # 1 falha transiente + 1 sucesso


def test_erro_nao_transiente_nao_retenta_e_vira_500(monkeypatch):
    erro = RuntimeError("ValidationException: agente invalido")
    fake = _setup(monkeypatch, FakeClient(erros=[erro, erro, erro]))
    resp = app.lambda_handler(_auth({"mensagem": "oi"}), None)
    assert resp["statusCode"] == 500
    assert len(fake.chamadas) == 1  # nao retenta o que nao e transiente
