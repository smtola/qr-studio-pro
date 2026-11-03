"""AI Agent: key store, client error mapping, tool sandbox, agent loop (mocked API, no network)."""
from __future__ import annotations

import json
import threading

import pytest

from src.ai import keystore
from src.ai.agent import MAX_HISTORY, run_turn, trim_history
from src.ai.client import AIError, ClaudeClient
from src.ai.tools import Toolbox
from src.convert import downloader as DL
from src.convert.common import ConvertError
from tests.test_convert_docs import make_text_pdf, make_xlsx  # noqa: F401


def fake(responses):
    calls = []

    def transport(url, headers, body, timeout):
        calls.append((url, headers, json.loads(body)))
        status, data = responses.pop(0)
        return status, json.dumps(data).encode()
    transport.calls = calls
    return transport


def msg(blocks, stop="end_turn"):
    return 200, {"content": blocks, "stop_reason": stop}


def test_keystore_roundtrip_and_mask(tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert keystore.get_key() == "" and keystore.get_model() == keystore.DEFAULT_MODEL
    keystore.save("sk-ant-abcdefghijklmnopqrstuvwxyz", "m1")
    assert keystore.get_key().startswith("sk-ant-") and keystore.get_model() == "m1"
    assert "abcdefgh" not in keystore.mask(keystore.get_key())
    keystore.clear_key()
    assert keystore.get_key() == "" and keystore.get_model() == "m1"
    assert keystore.looks_valid("sk-ant-abcdefghijklmnopqrstuvwxyz") and not keystore.looks_valid("hello")


@pytest.mark.parametrize("status,word", [(401, "rejected"), (429, "limiting"), (529, "busy"), (404, "model")])
def test_client_errors_are_friendly(status, word):
    c = ClaudeClient("sk-ant-x", "m", transport=fake([(status, {"error": {"message": "x"}})]))
    with pytest.raises(AIError, match=word):
        c.create([{"role": "user", "content": "hi"}])


def test_client_requires_key_and_sends_headers():
    with pytest.raises(AIError):
        ClaudeClient("", "m", transport=fake([])).create([])
    t = fake([msg([{"type": "text", "text": "ok"}])])
    ClaudeClient("sk-ant-k", "m", transport=t).create([{"role": "user", "content": "hi"}], system="s")
    url, headers, body = t.calls[0]
    assert url.startswith("https://api.anthropic.com/") and headers["x-api-key"] == "sk-ant-k" and body["system"] == "s"


def test_toolbox_sandbox_blocks_escape(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    assert "outside the work folder" in tb.run("list_files", {"subfolder": "../"})
    assert "outside the work folder" in tb.run("convert_document", {"operation": "pdf_to_word", "input": "/etc/passwd"})
    assert "unknown tool" in tb.run("rm_rf", {})


def test_toolbox_declined_creates_nothing(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: False)
    r = tb.run("make_qr", {"type": "url", "value": "https://example.com", "filename": "a.png"})
    assert "declined" in r and not list(tmp_path.iterdir())


def test_toolbox_make_qr_and_never_overwrites(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    r1 = tb.run("make_qr", {"type": "url", "value": "https://example.com", "filename": "a.png"})
    r2 = tb.run("make_qr", {"type": "url", "value": "https://example.com", "filename": "a.png"})
    assert r1.startswith("Created: a.png") and "a (2).png" in r2
    assert tb.run("make_qr", {"type": "url", "value": "not a url at all !!"}).startswith("Error:")


def test_toolbox_convert_and_list(tmp_path):
    make_xlsx(tmp_path / "t.xlsx")
    tb = Toolbox(tmp_path, lambda _t: True)
    assert "t.xlsx" in tb.run("list_files", {})
    r = tb.run("convert_document", {"operation": "excel_to_pdf", "input": "t.xlsx"})
    assert r.startswith("Created:") and (tmp_path / "t.pdf").exists()
    assert tb.run("pdf_tool", {"operation": "split_ranges", "inputs": ["t.pdf"]}).startswith("Error:")


def test_download_asks_with_rights_notice_and_uses_downloader(tmp_path, monkeypatch):
    asked = []
    tb = Toolbox(tmp_path, lambda t: asked.append(t) or True)

    def fake_dl(url, out, kind, quality, **kw):
        p = out / "v.mp4"
        p.write_bytes(b"x")
        return [p]
    monkeypatch.setattr(DL, "download", fake_dl)
    r = tb.run("download_media", {"url": "youtube.com/watch?v=abc"})
    assert r == "Created: v.mp4" and "permission" in asked[0] and "YouTube" in asked[0]
    assert tb.run("download_media", {"url": "javascript:alert(1)"}).startswith("Error:")


def test_agent_loop_runs_tool_then_answers(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    t = fake([
        msg([{"type": "text", "text": "Making it."}, {"type": "tool_use", "id": "t1", "name": "make_qr",
                                                      "input": {"type": "url", "value": "https://example.com", "filename": "q.png"}}], "tool_use"),
        msg([{"type": "text", "text": "Done: q.png"}]),
    ])
    events, hist = [], []
    out = run_turn(ClaudeClient("sk-ant-k", "m", transport=t), tb, hist, "make a qr", lambda k, v: events.append(k))
    assert out == "Done: q.png" and (tmp_path / "q.png").exists()
    assert events == ["text", "tool", "result"]
    assert hist[2]["content"][0]["type"] == "tool_result" and hist[2]["content"][0]["is_error"] is False
    assert t.calls[0][2]["tools"] and "system" in t.calls[0][2]


def test_agent_stops_after_max_steps_and_on_cancel(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    loop = (200, {"content": [{"type": "tool_use", "id": "x", "name": "list_files", "input": {}}], "stop_reason": "tool_use"})
    t = fake([loop] * 20)
    out = run_turn(ClaudeClient("sk-ant-k", "m", transport=t), tb, [], "go")
    assert "stopped" in out.lower() and len(t.calls) == 8
    ev = threading.Event()
    ev.set()
    assert run_turn(ClaudeClient("sk-ant-k", "m", transport=fake([])), tb, [], "go", cancel=ev) == "Stopped."


def test_trim_history_keeps_pairs():
    h = []
    for i in range(30):
        h += [{"role": "user", "content": f"q{i}"},
              {"role": "assistant", "content": [{"type": "tool_use", "id": str(i), "name": "n", "input": {}}]},
              {"role": "user", "content": [{"type": "tool_result", "tool_use_id": str(i), "content": "r"}]},
              {"role": "assistant", "content": [{"type": "text", "text": "a"}]}]
    trim_history(h)
    assert len(h) <= MAX_HISTORY + 4 and h[0]["role"] == "user" and isinstance(h[0]["content"], str)
