from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from screen_qa_assistant.models import ProviderProfile, VisionRequest
from screen_qa_assistant.providers.openai_compatible import OpenAICompatibleClient, OpenAICompatibleError


class StreamWorkerSignals(QObject):
    chunk = Signal(str)
    error = Signal(str)
    finished = Signal(str)


class StreamWorker:
    def __init__(
        self,
        client: OpenAICompatibleClient,
        provider: ProviderProfile,
        request: VisionRequest,
        api_key: str | None,
    ) -> None:
        self.client = client
        self.provider = provider
        self.request = request
        self.api_key = api_key
        self.stop_event = threading.Event()
        self.signals = StreamWorkerSignals()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self) -> None:
        try:
            for chunk in self.client.stream_chat(
                self.provider,
                self.request,
                self.api_key,
                stop_event=self.stop_event,
            ):
                if self.stop_event.is_set():
                    self.signals.finished.emit("cancelled")
                    return
                self.signals.chunk.emit(chunk)
        except OpenAICompatibleError as exc:
            self.signals.error.emit(str(exc))
            self.signals.finished.emit("error")
            return
        except Exception as exc:  # pragma: no cover - UI 兜底
            self.signals.error.emit(f"发生未预期错误：{exc}")
            self.signals.finished.emit("error")
            return

        if self.stop_event.is_set():
            self.signals.finished.emit("cancelled")
        else:
            self.signals.finished.emit("completed")
