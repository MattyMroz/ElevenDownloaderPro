"""Constants of the ElevenReader web route: voices, addresses, timings and page scripts."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from .types import ElevenReaderVoice

__all__ = [
    "ACTION_TIMEOUT_S",
    "ADD_ENDPOINT",
    "API_HOST",
    "CHROME_LOCATIONS",
    "CHROME_STEM",
    "CLEANUP_STEP_TIMEOUT_S",
    "CONNECT_ATTEMPTS",
    "CONNECT_INTERVAL_S",
    "DEFAULT_VOICE_ALIAS",
    "DOCUMENT_NAME",
    "END_IDLE_S",
    "END_SLACK_CHARS",
    "LIBRARY_LOAD_S",
    "LIBRARY_URL",
    "LINE_SEPARATOR",
    "MAX_DOCUMENT_CHARS",
    "MAX_PARALLEL_DOCUMENTS",
    "MIN_DEDUP_BYTES",
    "MIN_PROBE_CHARS",
    "PAGE_SPEED",
    "PLAYER_STATE_JS",
    "PLAY_ATTEMPTS",
    "POLL_S",
    "READING_SPEED",
    "READS_URL",
    "READY_TIMEOUT_S",
    "SIGN_IN_TIMEOUT_S",
    "SILENT_CHUNK_MIN_LETTERS",
    "SILENT_CHUNK_MS_PER_LETTER",
    "SPEED_CHECK_S",
    "SPEED_JS",
    "SPEED_STATE_JS",
    "SPEED_TOLERANCE",
    "STALL_S",
    "START_TIMEOUT_S",
    "STREAM_PATH",
    "TAIL_CHARS",
    "UNAVAILABLE_RETRY_S",
    "USER_CONFIG_URL",
    "VOICES",
]


# ── Constants ─────────────────────────────────────────────────────────────────

VOICES: Final[MappingProxyType[str, ElevenReaderVoice]] = MappingProxyType(
    {
        "fronczewski": ElevenReaderVoice(
            alias="fronczewski", label="Piotr Fronczewski", voice_id="T5l58N8RNz5DKoClpKIJ"
        ),
        "adam": ElevenReaderVoice(alias="adam", label="Adam", voice_id="hIssydxXZ1WuDorjx6Ic"),
    },
)
"""Voices offered for ElevenReader, keyed by stable alias in display order."""

DEFAULT_VOICE_ALIAS: Final[str] = "fronczewski"
"""Alias of the voice selected when the settings name none."""

MAX_DOCUMENT_CHARS: Final[int] = 50_000
"""Largest document text uploaded in one attempt."""

MAX_PARALLEL_DOCUMENTS: Final[int] = 2
"""Most documents recorded at once in tabs of the one Chrome; a third stream on the device closes an older one."""

LINE_SEPARATOR: Final[str] = "…"
"""Paragraph placed between lines so ElevenReader pauses; never spoken and never a line itself."""

DOCUMENT_NAME: Final[str] = "edp.txt"
"""Name of the uploaded file; the library titles the document by its first sentence instead."""

LIBRARY_URL: Final[str] = "https://elevenreader.io/reader/library"
"""Library page with the Import button; a document opens under it by read id."""

API_HOST: Final[str] = "api.elevenlabs.io"
"""Host whose requests carry the page's authorization token."""

ADD_ENDPOINT: Final[str] = "/v1/reader/reads/add/v2"
"""Request path made by the Upload button; its JSON response carries the new read id."""

USER_CONFIG_URL: Final[str] = "https://api.elevenlabs.io/v1/reader/user_config"
"""Account settings holding the default voice and the playback speed."""

READS_URL: Final[str] = "https://api.elevenlabs.io/v1/reader/reads"
"""Collection of uploaded reads; one read is deleted under its id."""

STREAM_PATH: Final[str] = "/v1/reader/reads/stream/v2/"
"""WebSocket path streaming audio and character timings of one read."""

PAGE_SPEED: Final[float] = 64.0
"""Playback rate forced on the page's audio buffers while recording."""

READING_SPEED: Final[float] = 1.0
"""Account reading speed at which the server streams Eleven v4 instead of v2."""

SPEED_TOLERANCE: Final[float] = 0.01
"""Playback-rate difference from the target that still counts as the target."""

READY_TIMEOUT_S: Final[float] = 600.0
"""Wait for a document to become playable after upload."""

ACTION_TIMEOUT_S: Final[float] = 120.0
"""Time allowed for one click, upload or page load; the site can lag for tens of seconds."""

LIBRARY_LOAD_S: Final[float] = 45.0
"""Wait for the library to show its Import button before the site counts as unavailable."""

UNAVAILABLE_RETRY_S: Final[float] = 60.0
"""Retry delay suggested to the caller when the site or browser is unavailable."""

POLL_S: Final[float] = 1.0
"""Recording loop tick."""

SPEED_CHECK_S: Final[float] = 3.0
"""Interval between checks that the page still plays at the target speed."""

START_TIMEOUT_S: Final[float] = 60.0
"""Wait for the first audio after pressing Play."""

PLAY_ATTEMPTS: Final[int] = 3
"""Presses of Play within one attempt before the missing audio counts as a timeout."""

STALL_S: Final[float] = 300.0
"""Time without new audio before the end after which the attempt times out."""

END_IDLE_S: Final[float] = 10.0
"""Quiet time after the end of the text before the recording counts as complete."""

END_SLACK_CHARS: Final[int] = 30
"""Player position this close to the end counts as the end; at high speed it can hang on the final pause."""

MIN_DEDUP_BYTES: Final[int] = 8 * 1024
"""Smaller audio chunks are pauses that may legitimately repeat byte for byte, so they are never skipped."""

TAIL_CHARS: Final[int] = 20_000
"""Recent text kept to recognise what a reconnected stream sends again."""

MIN_PROBE_CHARS: Final[int] = 10
"""Leading characters of the first chunk after a reconnect searched for in the recent text."""

SILENT_CHUNK_MIN_LETTERS: Final[int] = 20
"""Fewest letters in a chunk judged for missing speech; shorter chunks can be naturally brief."""

SILENT_CHUNK_MS_PER_LETTER: Final[float] = 10.0
"""Audio per letter below which a chunk carries text without speech; silent chunks measured 1.5, healthy 20+."""

CONNECT_ATTEMPTS: Final[int] = 30
"""Attempts to attach to a freshly started Chrome."""

CONNECT_INTERVAL_S: Final[float] = 0.5
"""Pause between attach attempts while Chrome starts."""

CLEANUP_STEP_TIMEOUT_S: Final[float] = 15.0
"""Deadline of one account cleanup step."""

SIGN_IN_TIMEOUT_S: Final[float] = 600.0
"""Time the sign-in window waits for the owner to sign in."""

CHROME_STEM: Final[str] = "chrome"
"""Executable stem of Google Chrome looked up on ``PATH``."""

CHROME_LOCATIONS: Final[tuple[tuple[str, str], ...]] = (
    ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
    ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
)
"""Standard Google Chrome install locations under environment-variable roots."""

SPEED_JS: Final[str] = """
(() => {
    if (window.__edpState) return;
    window.__edpSpeed = __INITIAL_SPEED__;
    const playing = new Set();
    const contexts = new WeakSet();
    let contextCount = 0;
    window.__edpSetSpeed = (speed) => {
        window.__edpSpeed = speed;
        for (const src of playing) {
            try { src.playbackRate.value = speed; } catch (e) {}
        }
    };
    window.__edpState = () => ({
        target: window.__edpSpeed,
        rates: [...playing].map((src) => src.playbackRate.value),
        contexts: contextCount,
    });
    for (const Ctx of [window.AudioContext, window.webkitAudioContext]) {
        if (!Ctx) continue;
        const originalCreate = Ctx.prototype.createBufferSource;
        Ctx.prototype.createBufferSource = function () {
            if (!contexts.has(this)) {
                contexts.add(this);
                contextCount += 1;
            }
            const src = originalCreate.call(this);
            const originalStart = src.start;
            src.start = function () {
                if (window.__edpSpeed !== 1) {
                    try { src.playbackRate.value = window.__edpSpeed; } catch (e) {}
                }
                playing.add(src);
                src.addEventListener("ended", () => playing.delete(src));
                return originalStart.apply(this, arguments);
            };
            return src;
        };
    }
})();
"""
"""Init script playing page audio buffers at ``window.__edpSpeed``; ``__INITIAL_SPEED__`` is substituted."""

SPEED_STATE_JS: Final[str] = "() => window.__edpState ? window.__edpState() : null"
"""Read the speed script state of a frame, or null when the script is absent."""

PLAYER_STATE_JS: Final[str] = """
() => {
    const slider = document.querySelector('input[type=range], [role=slider]');
    const value = slider ? Number(slider.value || slider.getAttribute('aria-valuenow')) : 0;
    const max = slider ? Number(slider.max || slider.getAttribute('aria-valuemax')) : 0;
    return {value, max};
}
"""
"""Report the player position and the document length, both in characters."""
