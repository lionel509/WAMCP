from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from mcp.server.fastmcp import FastMCP

from app.main import create_app
from app.mcp import server as mcp_server
from app.mcp import tools


class DummyScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class DummyAllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class DummySession:
    def __init__(self, results):
        self._results = list(results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        return self._results.pop(0)

    async def commit(self):
        return None


@asynccontextmanager
async def _no_audit_db():
    yield None


def _paths(app):
    return {route.path for route in app.routes if isinstance(route, APIRoute)}


def test_webhooks_disabled_in_plugin_mode():
    app = create_app(plugin_mode=True)
    paths = _paths(app)
    assert "/webhooks/whatsapp" not in paths
    assert "/send/text" not in paths
    assert "/admin/conversations" not in paths
    assert "/health" in paths


def test_webhooks_present_when_plugin_mode_off():
    app = create_app(plugin_mode=False)
    paths = _paths(app)
    assert "/webhooks/whatsapp" in paths
    assert "/send/text" in paths


def test_mcp_server_tools_registered():
    assert isinstance(mcp_server.mcp, FastMCP)
    for fn in ("list_conversations", "get_recent_messages", "search_messages", "list_documents"):
        assert hasattr(mcp_server, fn)


@pytest.mark.asyncio
async def test_tools_return_sources_and_scope(monkeypatch):
    convo = SimpleNamespace(id="c1", type=SimpleNamespace(value="individual"), display_name="Test", updated_at=datetime(2024, 1, 1))
    dummy_session = DummySession([DummyScalarResult([convo])])
    monkeypatch.setattr(tools, "AsyncSessionLocal", lambda: dummy_session)
    monkeypatch.setattr(tools, "get_audit_db", _no_audit_db)
    monkeypatch.setattr(tools.settings, "PUBLIC_BASE_URL", "https://example.com")

    res = await tools.list_conversations(limit=1, offset=0)
    assert res["scope"]["conversation_ids"] == ["c1"]
    assert res["sources"][0]["kind"] == "conversation"
    assert res["sources"][0]["conversation_id"] == "c1"
    assert res["sources"][0]["permalink"].startswith("https://example.com")


@pytest.mark.asyncio
async def test_search_messages_sources_include_scope(monkeypatch):
    msg = SimpleNamespace(id="m1", conversation_id="c1", text_body="hello", sent_at=datetime(2024, 1, 2))
    dummy_session = DummySession([DummyScalarResult([msg])])
    monkeypatch.setattr(tools, "AsyncSessionLocal", lambda: dummy_session)
    monkeypatch.setattr(tools, "get_audit_db", _no_audit_db)

    res = await tools.search_messages("hello", limit=5, conversation_id="c1")
    assert res["scope"]["message_ids"] == ["m1"]
    assert res["sources"][0]["conversation_id"] == "c1"


@pytest.mark.asyncio
async def test_list_documents_sources_include_conversation(monkeypatch):
    doc = SimpleNamespace(
        id="d1",
        message_id="m1",
        doc_type=SimpleNamespace(value="pdf"),
        mime_type="application/pdf",
        extraction_status=SimpleNamespace(value="ok"),
        created_at=datetime(2024, 1, 3),
    )
    rows = [(doc, "c1", datetime(2024, 1, 2))]
    dummy_session = DummySession([DummyAllResult(rows)])
    monkeypatch.setattr(tools, "AsyncSessionLocal", lambda: dummy_session)
    monkeypatch.setattr(tools, "get_audit_db", _no_audit_db)

    res = await tools.list_documents(limit=1)
    assert res["scope"]["document_ids"] == ["d1"]
    assert res["scope"]["conversation_ids"] == ["c1"]
    assert res["sources"][0]["conversation_id"] == "c1"
