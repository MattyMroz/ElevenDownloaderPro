from __future__ import annotations

import asyncio
import base64
import json
import math
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from edp.engine import ElevenReaderConfig, ElevenReaderTtsEngine, resolve_voice
from edp.engine.api_backend import document_titles
from edp.engine.service import part_spans
from edp.engine.types import (
    AlignmentChunk,
    DocumentResult,
    DocumentSynthesisRequest,
    DocumentTrace,
    LibraryState,
    PlayerState,
    UploadedRead,
)
from edp.errors import TtsProviderUnavailableError
from edp.utils.mp3_frames import frames_duration_ms

if TYPE_CHECKING:
    from collections.abc import Callable

    from edp.cancellation import Cancellation
    from edp.engine.browser import ChromeSession
    from edp.engine.recorder import StreamRecorder
    from edp.engine.types import AccountCleanup

FRONCZEWSKI_ID = "T5l58N8RNz5DKoClpKIJ"
ADAM_ID = "hIssydxXZ1WuDorjx6Ic"
TOKEN = "token-7f3c9e1d5b"  # noqa: S105
READ_ID = "u:readsecret42"
FIRST_LINE = "Pierwsza kwestia."
READS_URL = "https://api.elevenlabs.io/v1/reader/reads"
LIBRARY_PAGE_URL = "https://elevenreader.io/reader/library"
ADD_URL = "https://api.elevenlabs.io/v1/reader/reads/add/v2"
SIGN_IN_BUTTON = "Sign in"
BREAK = '<break time="0.6s"/>'
FRAME_HEADER = bytes((0xFF, 0xFB, 0x90, 0x64))
FRAME_BYTES = 417
FRAME_MS = 1152 * 1000 / 44_100
BROKEN_FRAME = FRAME_HEADER + bytes(100)


def mp3_frames(count: int, *, fill: int = 0) -> bytes:
    frame: bytes = FRAME_HEADER + bytes([fill]) * (FRAME_BYTES - len(FRAME_HEADER))
    return frame * count


def audio_frame(
    chars: str,
    *,
    frames: int = 4,
    fill: int = 0,
    step_ms: float = 10.0,
    key: str = "alignment",
) -> str:
    payload: dict[str, object] = {"audio": base64.b64encode(mp3_frames(frames, fill=fill)).decode("ascii")}
    if chars:
        payload[key] = {
            "chars": list(chars),
            "charStartTimesMs": [index * step_ms for index in range(len(chars))],
            "charDurationsMs": [step_ms] * len(chars),
        }
    return json.dumps(payload)


def stream_frames(texts: tuple[str, ...]) -> list[str]:
    frames: list[str] = []
    for index, text in enumerate(texts):
        tail: str = f" {BREAK} … {BREAK} " if index < len(texts) - 1 else ' <break time="2s"/>'
        spoken: str = text.replace("[", "(").replace("]", ")")
        frames.append(audio_frame(spoken + tail, frames=22, fill=index + 1))
    return frames


def streamed_chars(texts: tuple[str, ...]) -> int:
    return sum(len(json.loads(frame)["alignment"]["chars"]) for frame in stream_frames(texts))


def document_trace(text: str = FIRST_LINE, *, listed_in_s: float = 0.0, read_id: str | None = None) -> DocumentTrace:
    pressed_at: float = time.time()
    return DocumentTrace(
        pressed_at=pressed_at, listed_by=pressed_at + listed_in_s, titles=document_titles(text), read_id=read_id
    )


def library_read(
    read_id: str,
    title: str = FIRST_LINE,
    *,
    added_at: float | None = None,
    imported: bool = True,
    file_type: str = "text/plain",
) -> dict[str, object]:
    return {
        "read_id": read_id,
        "canonical_read_id": read_id,
        "title": title,
        "description": title,
        "added_at_unix": int(time.time()) if added_at is None else int(added_at),
        "from_user_import": imported,
        "in_user_library": True,
        "original_file_type": file_type,
        "creation_status": "finished",
        "can_delete": True,
        "source": None,
        "url": None,
    }


def engine_config(root: Path, *, voice_id: str = "fronczewski") -> ElevenReaderConfig:
    return ElevenReaderConfig(voice=resolve_voice(voice_id), profile_root=root)


@dataclass
class FakeSite:
    texts: tuple[str, ...] = (FIRST_LINE, "Druga kwestia.")
    library: LibraryState = LibraryState.READY
    account: dict[str, object] = field(
        default_factory=lambda: {"default_voice_id": "previous-voice", "playback_speed_rate": 1.5, "theme": "dark"},
    )
    ignore_voice: bool = False
    voice_in_url: bool = True
    listening_speed: float = 1.0
    start_position: int = 0
    frames: list[str] | None = None
    char_count: int | None = None
    send_audio: bool = True
    player_done: bool = False
    hang_on: str = ""
    hung: threading.Event = field(default_factory=threading.Event)
    held: set[int] = field(default_factory=set)
    streams: int = 0
    upload_window_s: float = 120.0
    reads: list[str] = field(default_factory=list)
    page_type: type[FakePage] = field(default_factory=lambda: FakePage)
    failing: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    plays: int = 0
    sessions: list[FakeSession] = field(default_factory=list)
    pages: list[FakePage] = field(default_factory=list)

    def stream(self) -> list[str]:
        return stream_frames(self.texts) if self.frames is None else self.frames

    def count(self) -> int:
        if self.char_count is not None:
            return self.char_count
        return sum(len(json.loads(frame).get("alignment", {}).get("chars", [])) for frame in self.stream())


def read_id_of(upload: int) -> str:
    return READ_ID if upload == 0 else f"{READ_ID}-{upload}"


def read_url(upload: int) -> str:
    return f"{READS_URL}/{read_id_of(upload)}"


class FakePage:
    def __init__(self, site: FakeSite) -> None:
        self.site: FakeSite = site
        self.closed: bool = False
        self.watching: bool = False
        self.upload_index: int | None = None
        self._token: str | None = None
        self._recorder: StreamRecorder | None = None
        self._on_url: Callable[[str], None] | None = None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def open_library(self) -> LibraryState:
        await self._step("open_library")
        if self.site.library is LibraryState.READY:
            self._token = TOKEN
        return self.site.library

    async def library_ready(self) -> bool:
        return self.site.library is LibraryState.READY

    async def upload(self, document: Path, cleanup: AccountCleanup, save: Callable[[], None]) -> UploadedRead:
        text: str = document.read_text(encoding="utf-8")
        self.upload_index = len(self.site.uploaded)
        read_id: str = read_id_of(self.upload_index)
        self.site.uploaded.append(text)
        trace: DocumentTrace = document_trace(text, listed_in_s=self.site.upload_window_s)
        cleanup.documents.append(trace)
        save()
        self.site.reads.append(read_id)
        await self._step("upload")
        cleanup.swap(trace, replace(trace, read_id=read_id))
        return UploadedRead(read_id=read_id, char_count=self.site.count(), token=TOKEN)

    async def get_json(self, url: str, token: str, *, action: str) -> dict[str, object]:
        assert token == TOKEN
        await self._step(action)
        if action == "list_reads":
            assert url == READS_URL
            return {"reads": [library_read(read_id, self.site.texts[0]) for read_id in self.site.reads]}
        return dict(self.site.account)

    async def post_json(self, url: str, token: str, data: dict[str, object], *, action: str) -> None:
        assert token == TOKEN
        await self._step(action)
        updated: dict[str, object] = dict(data)
        if self.site.ignore_voice and action == "set_account":
            updated["default_voice_id"] = self.site.account["default_voice_id"]
        self.site.account = updated

    async def delete(self, url: str, token: str, *, action: str) -> None:
        assert token == TOKEN
        await self._step(action)
        self.site.deleted.append(url)
        read_id: str = url.removeprefix(f"{READS_URL}/")
        if read_id in self.site.reads:
            self.site.reads.remove(read_id)

    async def open_document(self, read_id: str) -> None:
        assert read_id == (READ_ID if self.upload_index is None else read_id_of(self.upload_index))
        await self._step("open_document")

    async def press_play(self) -> None:
        await self._step("press_play")
        self.site.plays += 1
        if self._recorder is None or self._on_url is None or not self.site.send_audio:
            return
        voice: str = str(self.site.account.get("default_voice_id")) if self.site.voice_in_url else "other"
        self.site.events.append(f"stream_{self.upload_index}")
        self.site.streams += 1
        self._on_url(f"wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{READ_ID}?voice_id={voice}")
        self._recorder.on_sent(
            json.dumps({"listening_speed": self.site.listening_speed, "position": self.site.start_position})
        )
        for frame in self.site.stream():
            self._recorder.on_frame(frame)

    async def player_state(self) -> PlayerState:
        await self._step("player_state")
        return PlayerState(value=100.0, length=100.0) if self.site.player_done else PlayerState(value=0.0, length=0.0)

    async def set_page_speed(self, speed: float) -> None:
        await self._step("set_page_speed")

    async def check_page_speed(self, speed: float) -> None:
        await self._step("check_page_speed")
        while self.upload_index in self.site.held:
            await asyncio.sleep(0.001)

    def watch_stream(self, recorder: StreamRecorder, on_url: Callable[[str], None]) -> None:
        self.watching = True
        self._recorder = recorder
        self._on_url = on_url

    def unwatch_stream(self) -> None:
        self.watching = False

    async def close(self) -> None:
        self.site.events.append("close_page")
        self.closed = True

    async def _step(self, action: str) -> None:
        self.site.events.append(action)
        if action in self.site.failing:
            message: str = f"fake {action} failed"
            raise TtsProviderUnavailableError(message)
        if action == self.site.hang_on:
            self.site.hung.set()
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            await future


class FakeSession:
    def __init__(self, site: FakeSite) -> None:
        self.site: FakeSite = site
        self.started: bool = False
        self.closed: bool = False

    @property
    def alive(self) -> bool:
        return self.started and not self.closed

    async def start(self) -> None:
        self.site.events.append("start_browser")
        self.started = True

    async def new_page(self) -> FakePage:
        page: FakePage = self.site.page_type(self.site)
        self.site.pages.append(page)
        return page

    async def close(self) -> None:
        self.site.events.append("close_browser")
        self.closed = True


def fake_engine(root: Path, site: FakeSite, *, voice_id: str = "fronczewski") -> ElevenReaderTtsEngine:
    def factory(profile_root: Path) -> ChromeSession:
        assert profile_root == root
        session: FakeSession = FakeSession(site)
        site.sessions.append(session)
        return cast("ChromeSession", session)

    return ElevenReaderTtsEngine(engine_config(root, voice_id=voice_id), browser_factory=factory)


class FakeRequest:
    def __init__(self, url: str, method: str, headers: dict[str, str]) -> None:
        self.url: str = url
        self.method: str = method
        self.headers: dict[str, str] = headers

    async def all_headers(self) -> dict[str, str]:
        return dict(self.headers)


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        body: object = None,
        *,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        authorization: str = TOKEN,
    ) -> None:
        self.status: int = status
        self.ok: bool = 200 <= status < 300
        self.headers: dict[str, str] = headers or {}
        self.url: str = ADD_URL
        self.request: FakeRequest = FakeRequest(
            ADD_URL, "POST", {"authorization": authorization} if authorization else {}
        )
        self._body: object = body
        self._text: str | None = text

    async def json(self) -> object:
        if self._text is not None:
            return json.loads(self._text)
        return self._body


class FakeApi:
    def __init__(self, page: FakePlaywrightPage) -> None:
        self.page: FakePlaywrightPage = page

    async def get(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
        return self.page.api_reply("GET", url, headers)

    async def post(self, url: str, *, headers: dict[str, str], data: dict[str, object]) -> FakeResponse:
        self.page.posted.append(data)
        return self.page.api_reply("POST", url, headers)

    async def delete(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
        return self.page.api_reply("DELETE", url, headers)


class FakeLocator:
    def __init__(self, page: FakePlaywrightPage, names: tuple[str, ...]) -> None:
        self.page: FakePlaywrightPage = page
        self.names: tuple[str, ...] = names

    @property
    def first(self) -> FakeLocator:
        return self

    def filter(self, *, visible: bool) -> FakeLocator:
        assert visible
        return self

    def or_(self, other: FakeLocator) -> FakeLocator:
        return FakeLocator(self.page, self.names + other.names)

    async def click(self) -> None:
        self.page.clicks.append(self.names[0])

    async def count(self) -> int:
        return sum(name in self.page.visible for name in self.names)

    async def wait_for(self, *, state: str = "visible", timeout: float | None = None) -> None:
        if self.page.wait_error is not None:
            raise self.page.wait_error
        if not any(name in self.page.visible for name in self.names):
            message: str = f"Timeout {timeout}ms exceeded"
            raise PlaywrightTimeoutError(message)

    async def set_input_files(self, files: Path) -> None:
        self.page.files.append(files)


class FakeExpectation:
    def __init__(self, page: FakePlaywrightPage, predicate: Callable[[FakeResponse], bool]) -> None:
        self.page: FakePlaywrightPage = page
        self.predicate: Callable[[FakeResponse], bool] = predicate

    async def __aenter__(self) -> FakeExpectation:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    @property
    def value(self) -> asyncio.Future[FakeResponse]:
        future: asyncio.Future[FakeResponse] = asyncio.get_running_loop().create_future()
        reply: FakeResponse | None = self.page.add_reply
        if reply is not None:
            assert self.predicate(reply)
            future.set_result(reply)
        return future


class FakeFrame:
    def __init__(self, state: object = None, *, error: Exception | None = None) -> None:
        self.state: object = state
        self.error: Exception | None = error
        self.scripts: list[str] = []

    async def evaluate(self, script: str) -> object:
        if self.error is not None:
            raise self.error
        self.scripts.append(script)
        return self.state if "__edpState()" in script else None


class FakeSocket:
    def __init__(self, url: str) -> None:
        self.url: str = url
        self.handlers: dict[str, Callable[[str | bytes], None]] = {}

    def on(self, event: str, handler: Callable[[str | bytes], None]) -> None:
        self.handlers[event] = handler


class FakePlaywrightPage:
    def __init__(self, *, visible: tuple[str, ...] = ("Import",), url: str = LIBRARY_PAGE_URL) -> None:
        self.visible: set[str] = set(visible)
        self.url: str = url
        self.goto_reply: FakeResponse | None = FakeResponse()
        self.goto_error: Exception | None = None
        self.wait_error: Exception | None = None
        self.close_error: Exception | None = None
        self.add_reply: FakeResponse | None = None
        self.replies: dict[tuple[str, str], FakeResponse] = {}
        self.request: FakeApi = FakeApi(self)
        self.frames: list[FakeFrame] = []
        self.player: object = None
        self.listeners: dict[str, list[Callable[..., None]]] = {}
        self.clicks: list[str] = []
        self.files: list[Path] = []
        self.posted: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []
        self.timeout_ms: float = 0.0
        self.closed: bool = False
        self.close_calls: int = 0

    def set_default_timeout(self, timeout_ms: float) -> None:
        self.timeout_ms = timeout_ms

    def on(self, event: str, handler: Callable[..., None]) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event: str, handler: Callable[..., None]) -> None:
        self.listeners[event].remove(handler)

    def emit(self, event: str, payload: object) -> None:
        for handler in list(self.listeners.get(event, [])):
            handler(payload)

    def is_closed(self) -> bool:
        return self.closed

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    async def goto(self, url: str) -> FakeResponse | None:
        self.calls.append(("GOTO", url))
        if self.goto_error is not None:
            raise self.goto_error
        return self.goto_reply

    def get_by_role(self, role: str, *, name: object, exact: bool = False) -> FakeLocator:
        assert role == "button"
        return FakeLocator(self, (name if isinstance(name, str) else SIGN_IN_BUTTON,))

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, (selector,))

    def expect_response(self, predicate: Callable[[FakeResponse], bool]) -> FakeExpectation:
        return FakeExpectation(self, predicate)

    async def evaluate(self, script: str) -> object:
        return self.player

    def api_reply(self, method: str, url: str, headers: dict[str, str]) -> FakeResponse:
        assert headers == {"authorization": TOKEN}
        self.calls.append((method, url))
        return self.replies.get((method, url), FakeResponse(200, {}))


def _no_browser(profile_root: Path) -> ChromeSession:
    message: str = f"scripted engine opened a browser on {profile_root}"
    raise AssertionError(message)


_pause = asyncio.sleep


class ScriptedEngine(ElevenReaderTtsEngine):
    def __init__(
        self,
        root: Path,
        *,
        speaks_up_to: dict[str, int] | None = None,
        failures: list[Exception] | None = None,
        lead_frames: int = 0,
        splices: bool = False,
    ) -> None:
        super().__init__(engine_config(root), browser_factory=_no_browser)
        self.lead_frames: int = lead_frames
        self.splices: bool = splices
        self.stops_at: dict[str, BaseException] = {}
        self.active: int = 0
        self.peak: int = 0
        self.speaks_up_to: dict[str, int] = speaks_up_to or {}
        self.failures: list[Exception] = failures or []
        self.documents: list[tuple[str, ...]] = []
        self.calls: int = 0
        self.closed: bool = False

    async def synthesize_document(self, request: DocumentSynthesisRequest, *, cancel: Cancellation) -> DocumentResult:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            for _ in range(10):
                await _pause(0)
        finally:
            self.active -= 1
        for part in request.parts:
            if part.text in self.stops_at:
                for _ in range(50):
                    await _pause(0)
                raise self.stops_at[part.text]
        number: int = len(self.documents)
        self.documents.append(tuple(part.request_id for part in request.parts))
        chunks: list[AlignmentChunk] = []
        audio: bytes = mp3_frames(self.lead_frames, fill=99)
        for index, part in enumerate(request.parts):
            last: bool = index == len(request.parts) - 1
            text: str = " ".join(part.text.replace("[", "(").replace("]", ")").split())
            text += ' <break time="2s"/>' if last else f" {BREAK} … {BREAK} "
            silent: bool = self.speaks_up_to.get(part.text, len(request.parts)) < len(request.parts)
            step_ms: float = 1.0 if silent else 10.0
            frames: int = 1 if silent else math.ceil(len(text) * step_ms / FRAME_MS) + 1
            chunk_audio: bytes = mp3_frames(frames, fill=number * 10 + index + 1)
            if self.splices:
                chunk_audio += BROKEN_FRAME
            chunks.append(
                AlignmentChunk(
                    offset_ms=frames_duration_ms(audio),
                    chars=tuple(text),
                    starts_ms=tuple(position * step_ms for position in range(len(text))),
                    durations_ms=(step_ms,) * len(text),
                    silent=silent,
                )
            )
            audio += chunk_audio
        request.recording.write_bytes(audio)
        return DocumentResult(
            request_id=request.request_id,
            recording=request.recording,
            voice_id=request.voice_id,
            request_time_ms=0.0,
            parts=part_spans(tuple(chunks), request.parts, tags=request.tags),
            chunks=tuple(chunks),
        )

    async def close(self) -> None:
        self.closed = True
        await super().close()
