from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from screen_qa_assistant.models import ChatMessage, ProviderProfile, VisionRequest
from screen_qa_assistant.providers.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleError,
)


def build_provider(base_url: str) -> ProviderProfile:
    return ProviderProfile(
        id="demo",
        name="Demo",
        base_url=base_url,
        api_key_ref=None,
        model="gpt-demo",
        supports_vision=True,
        enable_reasoning=False,
        timeout_seconds=1,
        temperature=0.1,
        max_tokens=512,
    )


def test_build_payload_includes_image_and_followups(tmp_path: Path) -> None:
    image_path = tmp_path / "capture.png"
    image_path.write_bytes(b"fake-image")
    request = VisionRequest(
        image_bytes_or_path=str(image_path),
        question="最后想问什么？",
        followup_messages=[
            ChatMessage(role="user", content="先前问题"),
            ChatMessage(role="assistant", content="先前回答"),
        ],
    )

    payload = OpenAICompatibleClient.build_payload(build_provider("https://example.com/v1"), request)

    assert payload["model"] == "gpt-demo"
    assert payload["stream"] is True
    assert payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert payload["messages"][-1] == {"role": "user", "content": "最后想问什么？"}


def test_build_payload_supports_text_only_reasoning_mode() -> None:
    provider = build_provider("https://example.com/v1").model_copy(update={"enable_reasoning": True})
    request = VisionRequest(
        image_bytes_or_path=None,
        question="直接帮我写一封邮件",
        followup_messages=[],
    )

    payload = OpenAICompatibleClient.build_payload(provider, request)

    assert payload["messages"] == [{"role": "user", "content": "直接帮我写一封邮件"}]
    assert payload["reasoning_effort"] == "medium"


def test_build_payload_switches_deepseek_chat_to_reasoner_when_reasoning_enabled() -> None:
    provider = build_provider("https://api.deepseek.com/v1").model_copy(
        update={
            "model": "deepseek-chat",
            "supports_vision": False,
            "enable_reasoning": True,
        }
    )
    request = VisionRequest(
        image_bytes_or_path=None,
        question="帮我做一个更深入的分析",
        followup_messages=[],
    )

    payload = OpenAICompatibleClient.build_payload(provider, request)

    assert payload["model"] == "deepseek-reasoner"
    assert "reasoning_effort" not in payload


def test_build_payload_does_not_switch_deepseek_chat_for_image_requests() -> None:
    provider = build_provider("https://api.deepseek.com/v1").model_copy(
        update={
            "model": "deepseek-chat",
            "supports_vision": True,
            "enable_reasoning": True,
        }
    )
    request = VisionRequest(
        image_bytes_or_path=b"fake-image",
        question="看看这张图",
        followup_messages=[],
    )

    payload = OpenAICompatibleClient.build_payload(provider, request)

    assert payload["model"] == "deepseek-chat"
    assert payload["reasoning_effort"] == "medium"


def test_build_payload_uses_high_reasoning_for_gpt54_and_omits_temperature() -> None:
    provider = build_provider("https://api.openai.com/v1").model_copy(
        update={
            "model": "gpt-5.4",
            "enable_reasoning": True,
            "temperature": 0.8,
        }
    )
    request = VisionRequest(
        image_bytes_or_path=None,
        question="请认真分析这个方案的风险",
        followup_messages=[],
    )

    payload = OpenAICompatibleClient.build_payload(provider, request)

    assert payload["model"] == "gpt-5.4"
    assert payload["reasoning_effort"] == "high"
    assert "temperature" not in payload


def test_parse_stream_lines_extracts_text() -> None:
    lines = [
        "data: {\"choices\": [{\"delta\": {\"content\": \"你好\"}}]}",
        "",
        "data: {\"choices\": [{\"delta\": {\"content\": \"，世界\"}}]}",
        "data: [DONE]",
    ]

    chunks = list(OpenAICompatibleClient.parse_stream_lines(lines))
    assert chunks == ["你好", "，世界"]


class StreamingHandler(BaseHTTPRequestHandler):
    mode = "ok"
    request_count = 0
    last_path = ""
    last_payload: dict | None = None

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/chat/completions", "/responses"}:
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        payload = json.loads(body.decode("utf-8")) if body else {}
        type(self).request_count += 1
        type(self).last_path = self.path
        type(self).last_payload = payload

        if self.mode == "401":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"bad key"}}')
            return

        if self.mode == "500":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"server error"}}')
            return

        if self.mode == "reasoning-fallback":
            if "reasoning_effort" in payload:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"unknown field reasoning_effort"}}')
                return

        if self.mode == "timeout":
            time.sleep(1.5)
            self.send_response(200)
            self.end_headers()
            return

        if self.mode == "responses-ok":
            if self.path != "/responses":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for line in [
                'data: {"type":"response.output_text.delta","delta":"第一段"}\n\n',
                'data: {"type":"response.output_text.delta","delta":"第二段"}\n\n',
                'data: {"type":"response.completed"}\n\n',
            ]:
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for line in [
            'data: {"choices":[{"delta":{"content":"第一段"}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"第二段"}}]}\n\n',
            "data: [DONE]\n\n",
        ]:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def run_server(mode: str) -> tuple[HTTPServer, threading.Thread]:
    handler = type("ModeHandler", (StreamingHandler,), {"mode": mode})
    handler.request_count = 0
    handler.last_path = ""
    handler.last_payload = None
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def build_request(tmp_path: Path) -> VisionRequest:
    image_path = tmp_path / "capture.png"
    image_path.write_bytes(b"fake-image")
    return VisionRequest(
        image_bytes_or_path=str(image_path),
        question="图里是什么？",
        followup_messages=[],
    )


def test_stream_chat_returns_chunks(tmp_path: Path) -> None:
    server, thread = run_server("ok")
    client = OpenAICompatibleClient()
    provider = build_provider(f"http://127.0.0.1:{server.server_port}")

    try:
        chunks = list(client.stream_chat(provider, build_request(tmp_path), api_key=None))
    finally:
        server.shutdown()
        thread.join()

    assert "".join(chunks) == "第一段第二段"


def test_stream_chat_uses_responses_api_for_gpt54_reasoning() -> None:
    server, thread = run_server("responses-ok")
    client = OpenAICompatibleClient()
    provider = build_provider(f"http://127.0.0.1:{server.server_port}").model_copy(
        update={"model": "gpt-5.4", "enable_reasoning": True}
    )
    request = VisionRequest(
        image_bytes_or_path=None,
        question="请深入分析这段文本",
        followup_messages=[],
    )

    try:
        chunks = list(client.stream_chat(provider, request, api_key=None))
        request_count = server.RequestHandlerClass.request_count
        last_path = server.RequestHandlerClass.last_path
        last_payload = server.RequestHandlerClass.last_payload
    finally:
        server.shutdown()
        thread.join()

    assert "".join(chunks) == "第一段第二段"
    assert request_count == 1
    assert last_path == "/responses"
    assert last_payload["model"] == "gpt-5.4"
    assert last_payload["reasoning"] == {"effort": "high"}


def test_stream_chat_retries_without_reasoning_when_endpoint_rejects_field(tmp_path: Path) -> None:
    server, thread = run_server("reasoning-fallback")
    client = OpenAICompatibleClient()
    provider = build_provider(f"http://127.0.0.1:{server.server_port}").model_copy(update={"enable_reasoning": True})

    try:
        chunks = list(client.stream_chat(provider, build_request(tmp_path), api_key=None))
        request_count = server.RequestHandlerClass.request_count
    finally:
        server.shutdown()
        thread.join()

    assert "".join(chunks) == "第一段第二段"
    assert request_count == 2


@pytest.mark.parametrize("mode,expected", [("401", "bad key"), ("500", "server error"), ("timeout", "超时")])
def test_stream_chat_raises_meaningful_errors(tmp_path: Path, mode: str, expected: str) -> None:
    server, thread = run_server(mode)
    client = OpenAICompatibleClient()
    provider = build_provider(f"http://127.0.0.1:{server.server_port}")

    try:
        with pytest.raises(OpenAICompatibleError) as excinfo:
            list(client.stream_chat(provider, build_request(tmp_path), api_key=None))
    finally:
        server.shutdown()
        thread.join()

    assert expected in str(excinfo.value)
