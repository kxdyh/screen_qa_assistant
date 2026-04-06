from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Iterable, Iterator

import httpx

from screen_qa_assistant.models import ChatMessage, ProviderProfile, VisionRequest


class OpenAICompatibleError(RuntimeError):
    pass


class OpenAICompatibleClient:
    @staticmethod
    def _uses_gpt5_reasoning_family(provider: ProviderProfile) -> bool:
        model = provider.model.lower()
        return model.startswith("gpt-5.4") or model.startswith("gpt-5.2")

    @staticmethod
    def _uses_dedicated_reasoning_model(provider: ProviderProfile, request: VisionRequest) -> bool:
        return (
            provider.enable_reasoning
            and provider.model == "deepseek-chat"
            and request.image_bytes_or_path is None
        )

    @staticmethod
    def _resolve_effective_provider(provider: ProviderProfile, request: VisionRequest) -> ProviderProfile:
        if OpenAICompatibleClient._uses_dedicated_reasoning_model(provider, request):
            return provider.model_copy(update={"model": "deepseek-reasoner"})
        return provider

    @staticmethod
    def _resolve_reasoning_effort(provider: ProviderProfile, request: VisionRequest) -> str | None:
        if not provider.enable_reasoning:
            return None
        if OpenAICompatibleClient._uses_dedicated_reasoning_model(provider, request):
            return None
        if OpenAICompatibleClient._uses_gpt5_reasoning_family(provider):
            return "high"
        return "medium"

    @staticmethod
    def _should_use_responses_api(provider: ProviderProfile, request: VisionRequest) -> bool:
        return provider.enable_reasoning and OpenAICompatibleClient._uses_gpt5_reasoning_family(provider)

    @staticmethod
    def _encode_image(image_bytes_or_path: bytes | str) -> str:
        if isinstance(image_bytes_or_path, bytes):
            image_bytes = image_bytes_or_path
        else:
            image_bytes = Path(image_bytes_or_path).read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def build_payload(provider: ProviderProfile, request: VisionRequest) -> dict:
        uses_dedicated_reasoning_model = OpenAICompatibleClient._uses_dedicated_reasoning_model(provider, request)
        reasoning_effort = OpenAICompatibleClient._resolve_reasoning_effort(provider, request)
        provider = OpenAICompatibleClient._resolve_effective_provider(provider, request)
        messages: list[dict]
        if request.image_bytes_or_path is not None:
            image_url = OpenAICompatibleClient._encode_image(request.image_bytes_or_path)
            if request.followup_messages:
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请持续参考这张截图，并结合后续对话回答问题。"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ]
                messages.extend(
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                    for message in request.followup_messages
                )
                messages.append({"role": "user", "content": request.question})
            else:
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": request.question},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ]
        elif request.followup_messages:
            messages = [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in request.followup_messages
            ]
            messages.append({"role": "user", "content": request.question})
        else:
            messages = [{"role": "user", "content": request.question}]

        payload = {
            "model": provider.model,
            "stream": True,
            "max_tokens": provider.max_tokens,
            "messages": messages,
        }
        if not (reasoning_effort and OpenAICompatibleClient._uses_gpt5_reasoning_family(provider)):
            payload["temperature"] = provider.temperature
        if reasoning_effort and not uses_dedicated_reasoning_model:
            payload["reasoning_effort"] = reasoning_effort
        return payload

    @staticmethod
    def build_responses_payload(provider: ProviderProfile, request: VisionRequest) -> dict:
        reasoning_effort = OpenAICompatibleClient._resolve_reasoning_effort(provider, request)
        provider = OpenAICompatibleClient._resolve_effective_provider(provider, request)

        input_items: list[dict]
        if request.image_bytes_or_path is not None:
            image_url = OpenAICompatibleClient._encode_image(request.image_bytes_or_path)
            if request.followup_messages:
                input_items = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "请持续参考这张截图，并结合后续对话回答问题。"},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    }
                ]
                input_items.extend(
                    {"role": message.role, "content": message.content}
                    for message in request.followup_messages
                )
                input_items.append({"role": "user", "content": request.question})
            else:
                input_items = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": request.question},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    }
                ]
        elif request.followup_messages:
            input_items = [
                {"role": message.role, "content": message.content}
                for message in request.followup_messages
            ]
            input_items.append({"role": "user", "content": request.question})
        else:
            input_items = [{"role": "user", "content": request.question}]

        payload = {
            "model": provider.model,
            "stream": True,
            "max_output_tokens": provider.max_tokens,
            "input": input_items,
        }
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        return payload

    @staticmethod
    def parse_stream_lines(lines: Iterable[str]) -> Iterator[str]:
        for raw_line in lines:
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                        yield str(item["text"])

    @staticmethod
    def parse_responses_stream_lines(lines: Iterable[str]) -> Iterator[str]:
        for raw_line in lines:
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            event_type = data.get("type")
            if event_type in {"response.output_text.delta", "response.refusal.delta"}:
                delta = data.get("delta")
                if isinstance(delta, str) and delta:
                    yield delta

    @staticmethod
    def _build_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    @staticmethod
    def _build_responses_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        return f"{normalized}/responses"

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            response.read()
            payload = response.json()
        except Exception:
            return f"请求失败，状态码 {response.status_code}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if payload.get("message"):
                return str(payload["message"])
        return f"请求失败，状态码 {response.status_code}"

    @staticmethod
    def _is_reasoning_rejection(response: httpx.Response) -> bool:
        if response.status_code not in {400, 404, 422}:
            return False
        try:
            response.read()
            body = response.text.lower()
        except Exception:
            return False
        keywords = ("reasoning", "reasoning_effort", "unknown field", "unsupported", "extra input")
        return any(keyword in body for keyword in keywords)

    def stream_chat(
        self,
        provider: ProviderProfile,
        request: VisionRequest,
        api_key: str | None,
        stop_event: threading.Event | None = None,
    ) -> Iterator[str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if self._should_use_responses_api(provider, request):
            yield from self._stream_responses(provider, request, headers, stop_event)
            return

        url = self._build_url(provider.base_url)

        try:
            with httpx.Client(timeout=provider.timeout_seconds, trust_env=False) as client:
                allow_reasoning = provider.enable_reasoning
                while True:
                    payload = self.build_payload(
                        provider.model_copy(update={"enable_reasoning": allow_reasoning}),
                        request,
                    )
                    with client.stream("POST", url, headers=headers, json=payload) as response:
                        if response.status_code != 200:
                            if allow_reasoning and self._is_reasoning_rejection(response):
                                allow_reasoning = False
                                continue
                            raise OpenAICompatibleError(self._extract_error_message(response))
                        for line in response.iter_lines():
                            if stop_event and stop_event.is_set():
                                return
                            for chunk in self.parse_stream_lines([line]):
                                if stop_event and stop_event.is_set():
                                    return
                                yield chunk
                        return
        except httpx.TimeoutException as exc:
            raise OpenAICompatibleError("请求超时") from exc
        except httpx.HTTPError as exc:
            raise OpenAICompatibleError(f"网络请求失败：{exc}") from exc

    def _stream_responses(
        self,
        provider: ProviderProfile,
        request: VisionRequest,
        headers: dict[str, str],
        stop_event: threading.Event | None,
    ) -> Iterator[str]:
        url = self._build_responses_url(provider.base_url)
        payload = self.build_responses_payload(provider, request)

        try:
            with httpx.Client(timeout=provider.timeout_seconds, trust_env=False) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        message = self._extract_error_message(response)
                        if response.status_code in {400, 404, 405}:
                            message = f"当前端点不支持 Responses API，无法启用 GPT-5 思考模式：{message}"
                        raise OpenAICompatibleError(message)
                    for line in response.iter_lines():
                        if stop_event and stop_event.is_set():
                            return
                        for chunk in self.parse_responses_stream_lines([line]):
                            if stop_event and stop_event.is_set():
                                return
                            yield chunk
        except httpx.TimeoutException as exc:
            raise OpenAICompatibleError("请求超时") from exc
        except httpx.HTTPError as exc:
            raise OpenAICompatibleError(f"网络请求失败：{exc}") from exc
