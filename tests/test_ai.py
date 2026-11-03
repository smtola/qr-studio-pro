"""AI Agent: key store, client error mapping, tool sandbox, agent loop (mocked API, no network)."""
from __future__ import annotations

import json
import threading

import pytest

from src.ai import keystore
from src.ai.agent import MAX_HISTORY, run_turn, trim_history
from src.ai.client import AIError, GroqClient
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


KEY = "gsk_abcdefghijklmnopqrstuvwxyz"


def reply(text="", calls=None):
    m = {"role": "assistant", "content": text}
    if calls:
        m["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a) if isinstance(a, dict) else a}}
                           for i, (n, a) in enumerate(calls)]
    return 200, {"choices": [{"message": m, "finish_reason": "tool_calls" if calls else "stop"}]}


def test_keystore_roundtrip_and_mask(tmp_path, monkeypatch):
    monkeypatch.setenv("QRSP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert keystore.get_key() == "" and keystore.get_model() == keystore.DEFAULT_MODEL
    keystore.save(KEY, "m1")
    assert keystore.get_key().startswith("gsk_") and keystore.get_model() == "m1"
    assert "abcdefgh" not in keystore.mask(keystore.get_key())
    keystore.clear_key()
    assert keystore.get_key() == "" and keystore.get_model() == "m1"
    assert keystore.looks_valid(KEY) and not keystore.looks_valid("hello") and not keystore.looks_valid("sk-ant-abcdefghijklmnopqrstuvwxyz")


@pytest.mark.parametrize("status,word", [(401, "rejected"), (429, "limiting"), (503, "busy"), (404, "model")])
def test_client_errors_are_friendly(status, word):
    c = GroqClient(KEY, "m", transport=fake([(status, {"error": {"message": "x"}})]))
    with pytest.raises(AIError, match=word):
        c.create([{"role": "user", "content": "hi"}])


def test_client_requires_key_and_sends_headers():
    with pytest.raises(AIError):
        GroqClient("", "m", transport=fake([])).create([])
    t = fake([reply("ok")])
    r = GroqClient(KEY, "m", transport=t).create([{"role": "user", "content": "hi"}], system="s", tools=[{"type": "function"}])
    url, headers, body = t.calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions" and headers["authorization"] == f"Bearer {KEY}"
    assert body["messages"][0] == {"role": "system", "content": "s"} and body["tool_choice"] == "auto"
    assert r["message"]["content"] == "ok"


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
        reply("Making it.", [("make_qr", {"type": "url", "value": "https://example.com", "filename": "q.png"})]),
        reply("Done: q.png"),
    ])
    events, hist = [], []
    out = run_turn(GroqClient(KEY, "m", transport=t), tb, hist, "make a qr", lambda k, v: events.append(k))
    assert out == "Done: q.png" and (tmp_path / "q.png").exists()
    assert events == ["text", "tool", "result"]
    assert hist[2]["role"] == "tool" and hist[2]["tool_call_id"] == "c0" and hist[2]["content"].startswith("Created")
    body = t.calls[0][2]
    assert body["tools"][0]["type"] == "function" and body["messages"][0]["role"] == "system"


def test_agent_bad_json_arguments_become_tool_error(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    t = fake([reply("", [("make_qr", "{not json")]), reply("sorry")])
    hist = []
    assert run_turn(GroqClient(KEY, "m", transport=t), tb, hist, "x") == "sorry"
    assert hist[2]["content"].startswith("Error:") and not list(tmp_path.iterdir())


def test_agent_stops_after_max_steps_and_on_cancel(tmp_path):
    tb = Toolbox(tmp_path, lambda _t: True)
    t = fake([reply("", [("list_files", {})]) for _ in range(20)])
    out = run_turn(GroqClient(KEY, "m", transport=t), tb, [], "go")
    assert "stopped" in out.lower() and len(t.calls) == 8
    ev = threading.Event()
    ev.set()
    assert run_turn(GroqClient(KEY, "m", transport=fake([])), tb, [], "go", cancel=ev) == "Stopped."


def test_trim_history_keeps_pairs():
    h = []
    for i in range(30):
        h += [{"role": "user", "content": f"q{i}"},
              {"role": "assistant", "content": "", "tool_calls": [{"id": str(i), "type": "function", "function": {"name": "n", "arguments": "{}"}}]},
              {"role": "tool", "tool_call_id": str(i), "content": "r"},
              {"role": "assistant", "content": "a"}]
    trim_history(h)
    assert len(h) <= MAX_HISTORY + 4 and h[0]["role"] == "user" and isinstance(h[0]["content"], str)
