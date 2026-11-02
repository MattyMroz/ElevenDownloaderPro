// ==UserScript==
// @name         EDP
// @namespace    https://github.com/MattyMroz/ElevenDownloaderPro
// @version      2.0.0
// @description  Records the ElevenReader audio stream from its first frame and saves MP3, word timings (.json) and sentence subtitles (.srt); can also upload pasted text, record it and restore the account afterwards.
// @author       Mateusz Mróz
// @match        https://elevenreader.io/*
// @noframes
// @run-at       document-start
// @grant        none
// @updateURL    https://raw.githubusercontent.com/MattyMroz/ElevenDownloaderPro/main/userscript/edp.user.js
// @downloadURL  https://raw.githubusercontent.com/MattyMroz/ElevenDownloaderPro/main/userscript/edp.user.js
// ==/UserScript==

(function () {
    "use strict";

    // ── Constants ────────────────────────────────────────────────────────────────

    const VERSION = "2.0.0";
    const VOICES = Object.freeze([
        Object.freeze({ alias: "fronczewski", label: "Piotr Fronczewski", voice_id: "T5l58N8RNz5DKoClpKIJ" }),
        Object.freeze({ alias: "adam", label: "Adam", voice_id: "hIssydxXZ1WuDorjx6Ic" }),
    ]);
    const LIBRARY_URL = "https://elevenreader.io/reader/library";
    const API_HOST = "api.elevenlabs.io";
    const ADD_ENDPOINT = "/v1/reader/reads/add/v2";
    const USER_CONFIG_URL = "https://api.elevenlabs.io/v1/reader/user_config";
    const READS_URL = "https://api.elevenlabs.io/v1/reader/reads";
    const STREAM_PATH = "/v1/reader/reads/stream/v2/";
    const DOCUMENT_NAME = "edp.txt";
    const PAGE_SPEED = 64.0;
    const READING_SPEED = 1.0;
    const MAX_DOCUMENT_CHARS = 50000;
    const LINE_SEPARATOR = "…";
    const PART_GLUE = `\n\n${LINE_SEPARATOR}\n\n`;
    const MIN_DEDUP_BYTES = 8 * 1024;
    const TAIL_CHARS = 20000;
    const MIN_PROBE_CHARS = 10;
    const SILENT_CHUNK_MIN_LETTERS = 20;
    const SILENT_CHUNK_MS_PER_LETTER = 10.0;
    const ACTION_TIMEOUT_S = 120.0;
    const READY_TIMEOUT_S = 600.0;
    const START_TIMEOUT_S = 60.0;
    const PLAY_ATTEMPTS = 3;
    const STALL_S = 300.0;
    const POLL_S = 1.0;
    const CLEANUP_STEP_TIMEOUT_S = 15.0;
    const JOB_KEY = "edp.job";
    const CLEANUP_KEY = "edp.cleanup";

    const PY_SPACE = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
    const SPACE_RUN = new RegExp(`[${PY_SPACE}]+`, "g");
    const IS_SPACE = new RegExp(`^[${PY_SPACE}]$`);
    const EDGE_SPACE = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, "g");
    const LINE_BREAK = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;
    const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;
    const TAG = /<[^>]*>/g;
    const LETTER = /[\p{L}\p{N}_]/gu;
    const BREAK_TAG = /<break[^>]*(?:\/>|$)/g;
    const BREAK_RUN = new RegExp(`<break[^>]*(?:>|$)(?:[${PY_SPACE}]*<break[^>]*(?:>|$))*`, "g");
    const SENTENCE_END = ".!?…";
    const CLOSING_MARKS = "\"'”’)]»";
    const DASHES = "-–—";

    // ── Python semantics ─────────────────────────────────────────────────────────

    function pySum(values) {
        let total = 0;
        let compensation = 0;
        for (const value of values) {
            const next = total + value;
            compensation += Math.abs(total) >= Math.abs(value) ? total - next + value : value - next + total;
            total = next;
        }
        return compensation && Number.isFinite(compensation) ? total + compensation : total;
    }

    function pyRound(value) {
        const floor = Math.floor(value);
        const fraction = value - floor;
        if (fraction !== 0.5) return fraction > 0.5 ? floor + 1 : floor;
        return floor % 2 === 0 ? floor : floor + 1;
    }

    function pyTruthy(value) {
        if (value === null || value === undefined) return false;
        if (Array.isArray(value)) return value.length > 0;
        if (typeof value === "object") return Object.keys(value).length > 0;
        return Boolean(value);
    }

    function isObject(value) {
        return typeof value === "object" && value !== null && !Array.isArray(value);
    }

    function isNumber(value) {
        return typeof value === "number";
    }

    function isSpace(char) {
        return IS_SPACE.test(char);
    }

    function collapseSpaces(text) {
        return text
            .split(SPACE_RUN)
            .filter((word) => word !== "")
            .join(" ");
    }

    function codePointMatches(pattern, text) {
        const before = new Int32Array(text.length + 1);
        let count = 0;
        for (let unit = 0; unit < text.length; unit += 1) {
            before[unit] = count;
            const high = text.charCodeAt(unit);
            const low = text.charCodeAt(unit + 1);
            if (high < 0xd800 || high > 0xdbff || !(low >= 0xdc00 && low <= 0xdfff)) count += 1;
            else {
                before[unit + 1] = count;
                unit += 1;
                count += 1;
            }
        }
        before[text.length] = count;
        return [...text.matchAll(pattern)].map((match) => [before[match.index], before[match.index + match[0].length]]);
    }

    // ── MP3 frames (port of utils/mp3_frames.py) ─────────────────────────────────

    const MPEG1_BITRATES_KBPS = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320];
    const MPEG2_BITRATES_KBPS = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160];
    const SAMPLE_RATES = { 0: [11025, 12000, 8000], 2: [22050, 24000, 16000], 3: [44100, 48000, 32000] };

    function parseFrameHeader(data, offset) {
        if (offset < 0 || offset + 4 > data.length) return null;
        const header = ((data[offset] << 24) | (data[offset + 1] << 16) | (data[offset + 2] << 8) | data[offset + 3]) >>> 0;
        if (header >>> 21 !== 0x7ff) return null;
        const version = (header >>> 19) & 0b11;
        const layer = (header >>> 17) & 0b11;
        const bitrateIndex = (header >>> 12) & 0b1111;
        const sampleRateIndex = (header >>> 10) & 0b11;
        if (version === 1 || layer !== 1 || bitrateIndex === 0 || bitrateIndex === 0b1111 || sampleRateIndex === 3) {
            return null;
        }
        const mpeg1 = version === 3;
        const bitrate = (mpeg1 ? MPEG1_BITRATES_KBPS : MPEG2_BITRATES_KBPS)[bitrateIndex] * 1000;
        const sampleRate = SAMPLE_RATES[version][sampleRateIndex];
        const padding = (header >>> 9) & 1;
        const samples = mpeg1 ? 1152 : 576;
        return {
            offset,
            size: Math.floor(((mpeg1 ? 144 : 72) * bitrate) / sampleRate) + padding,
            durationMs: (samples * 1000) / sampleRate,
        };
    }

    function audioOffset(data) {
        if (data.length < 3 || data[0] !== 0x49 || data[1] !== 0x44 || data[2] !== 0x33) return 0;
        if (data.length < 10) throw new Error("truncated ID3v2 header");
        const sizeBytes = data.subarray(6, 10);
        if (sizeBytes.some((byte) => byte & 0x80)) throw new Error("invalid ID3v2 size");
        const tagSize = sizeBytes.reduce((size, byte) => (size << 7) | byte, 0);
        return 10 + tagSize + (data[5] & 0x10 ? 10 : 0);
    }

    function validFrame(data, offset) {
        const frame = parseFrameHeader(data, offset);
        if (frame === null) return null;
        const following = offset + frame.size;
        return following + 4 > data.length || parseFrameHeader(data, following) !== null ? frame : null;
    }

    function* iterFrames(data) {
        let offset = audioOffset(data);
        while (offset + 4 <= data.length) {
            const frame = validFrame(data, offset);
            if (frame === null) {
                offset += 1;
                continue;
            }
            yield frame;
            offset += frame.size;
        }
    }

    function* serverFrames(data) {
        let expected = audioOffset(data);
        for (const frame of iterFrames(data)) {
            const dropped = parseFrameHeader(data, expected);
            if (frame.offset !== expected && dropped !== null) yield [expected, dropped.durationMs];
            yield [frame.offset, frame.durationMs];
            expected = frame.offset + frame.size;
        }
        const trailing = parseFrameHeader(data, expected);
        if (trailing !== null) yield [expected, trailing.durationMs];
    }

    function framesDurationMs(data) {
        return pySum(Array.from(serverFrames(data), ([, durationMs]) => durationMs));
    }

    function cutBeforeMs(data, cutMs) {
        let dropped = 0.0;
        for (const [offset, durationMs] of serverFrames(data)) {
            if (dropped >= cutMs - 0.5) return [data.subarray(offset), dropped];
            dropped += durationMs;
        }
        return [new Uint8Array(0), dropped];
    }

    // ── Stream recorder (port of engine/recorder.py) ─────────────────────────────

    function parseFrame(payload) {
        if (typeof payload !== "string") return { error: "binary stream frame ignored" };
        let data;
        try {
            data = JSON.parse(payload);
        } catch (error) {
            return { error: `stream frame is not JSON: ${error.message}` };
        }
        return isObject(data) ? { data } : { error: "stream frame is not a JSON object" };
    }

    function decodeBase64(text) {
        if (text.length % 4 !== 0 || !BASE64.test(text)) return null;
        const binary = atob(text);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        return bytes;
    }

    function frameAlignment(data) {
        const raw = pyTruthy(data.alignment) ? data.alignment : data.normalizedAlignment;
        if (!isObject(raw)) return null;
        const { chars, charStartTimesMs: starts, charDurationsMs: durations } = raw;
        if (!Array.isArray(chars) || chars.length === 0 || !Array.isArray(starts) || !Array.isArray(durations)) return null;
        if (chars.length !== starts.length || starts.length !== durations.length) return null;
        if (!starts.every(isNumber) || !durations.every(isNumber)) return null;
        return { chars: chars.map(String), startsMs: starts, durationsMs: durations };
    }

    function chunkDigest(bytes, chars) {
        let first = 0xdeadbeef ^ bytes.length;
        let second = 0x41c6ce57 ^ bytes.length;
        const feed = (value) => {
            first = Math.imul(first ^ value, 2654435761);
            second = Math.imul(second ^ value, 1597334677);
        };
        for (const byte of bytes) feed(byte);
        for (const char of JSON.stringify(chars)) feed(char.codePointAt(0));
        first = Math.imul(first ^ (first >>> 16), 2246822507) ^ Math.imul(second ^ (second >>> 13), 3266489909);
        second = Math.imul(second ^ (second >>> 16), 2246822507) ^ Math.imul(first ^ (first >>> 13), 3266489909);
        return `${bytes.length}:${(first >>> 0).toString(16)}:${(second >>> 0).toString(16)}`;
    }

    function startsWithAt(haystack, needle, at) {
        if (at < 0 || at + needle.length > haystack.length) return false;
        for (let index = 0; index < needle.length; index += 1) {
            if (haystack[at + index] !== needle[index]) return false;
        }
        return true;
    }

    function* rfindAll(haystack, needle) {
        for (let at = haystack.length - needle.length; at >= 0; at -= 1) {
            if (startsWithAt(haystack, needle, at)) yield at;
        }
    }

    function trimChunk(chunk, alignment, drop) {
        const [remaining, cutMs] = cutBeforeMs(chunk, alignment.startsMs[drop]);
        return [
            remaining,
            {
                chars: alignment.chars.slice(drop),
                startsMs: alignment.startsMs.slice(drop).map((start) => Math.max(0.0, start - cutMs)),
                durationsMs: alignment.durationsMs.slice(drop),
            },
        ];
    }

    function chunkLetters(text) {
        return (text.replace(TAG, "").match(LETTER) ?? []).length;
    }

    function isV2Speed(speed) {
        return speed !== null && speed !== READING_SPEED;
    }

    class StreamRecorder {
        constructor(onIssue = () => {}) {
            this.onIssue = onIssue;
            this.audio = [];
            this.offsetMs = 0.0;
            this.audioBytes = 0;
            this.chars = 0;
            this.chunks = [];
            this.seen = new Set();
            this.tail = [];
            this.expect = null;
            this.expectAnchored = false;
            this.listeningSpeed = null;
            this.final = false;
            this.stopped = false;
        }

        stop() {
            this.stopped = true;
        }

        onSent(payload) {
            if (this.stopped || typeof payload !== "string") return;
            let data;
            try {
                data = JSON.parse(payload);
            } catch {
                return;
            }
            const speed = isObject(data) ? data.listening_speed : undefined;
            if (isNumber(speed)) this.listeningSpeed = speed;
        }

        onFrame(payload) {
            if (this.stopped) return;
            const parsed = parseFrame(payload);
            if (parsed.error) {
                this.onIssue("error", parsed.error);
                return;
            }
            const data = parsed.data;
            if (data.type === "config" && this.chars) {
                this.expect = this.tail;
                this.expectAnchored = false;
            }
            const audio = data.audio;
            if (typeof audio === "string" && audio) {
                const chunk = decodeBase64(audio);
                if (chunk === null) this.onIssue("error", "stream frame carried undecodable audio");
                else this.writeChunk(chunk, frameAlignment(data));
            }
            if (data.isFinal === true) this.final = true;
        }

        writeChunk(chunk, alignment) {
            const chars = alignment === null ? [] : alignment.chars;
            if (chunk.length >= MIN_DEDUP_BYTES) {
                const digest = chunkDigest(chunk, chars);
                if (this.seen.has(digest)) return;
                this.seen.add(digest);
            }
            if (alignment !== null) {
                const repeated = this.repeatedPrefix(Array.from(chars.join("")));
                if (repeated === chars.length) return;
                if (repeated) [chunk, alignment] = trimChunk(chunk, alignment, repeated);
            }
            this.audio.push(chunk);
            this.audioBytes += chunk.length;
            const audioMs = framesDurationMs(chunk);
            if (alignment !== null) this.keepAlignment(alignment, audioMs);
            this.offsetMs += audioMs;
        }

        keepAlignment(alignment, audioMs) {
            const text = alignment.chars.join("");
            const letters = chunkLetters(text);
            const silent = letters >= SILENT_CHUNK_MIN_LETTERS && audioMs < SILENT_CHUNK_MS_PER_LETTER * letters;
            if (silent) {
                this.onIssue(
                    "warning",
                    `chunk ${this.chunks.length} carried text without speech: ${letters} letters in ${audioMs.toFixed(1)} ms of audio`,
                );
            }
            this.chunks.push({
                offsetMs: this.offsetMs,
                chars: alignment.chars,
                startsMs: alignment.startsMs,
                durationsMs: alignment.durationsMs,
                silent,
            });
            const codePoints = Array.from(text);
            this.chars += codePoints.length;
            this.tail = this.tail.concat(codePoints).slice(-TAIL_CHARS);
        }

        repeatedPrefix(text) {
            const expect = this.expect;
            if (expect === null) return 0;
            if (!this.expectAnchored && text.length < MIN_PROBE_CHARS) return 0;
            const starts = this.expectAnchored ? [0] : rfindAll(expect, text.slice(0, MIN_PROBE_CHARS));
            for (const at of starts) {
                if (startsWithAt(expect, text, at)) {
                    const rest = expect.slice(at + text.length);
                    this.expect = rest.length ? rest : null;
                    this.expectAnchored = true;
                    return text.length;
                }
                if (expect.length - at <= text.length && startsWithAt(text, expect.slice(at), 0)) {
                    this.expect = null;
                    return expect.length - at;
                }
            }
            this.expect = null;
            return 0;
        }
    }

    function sentPosition(payload) {
        if (typeof payload !== "string") return null;
        let data;
        try {
            data = JSON.parse(payload);
        } catch {
            return null;
        }
        return isObject(data) && isNumber(data.position) ? data.position : null;
    }

    // ── Document (port of engine/service.py) ─────────────────────────────────────

    function neutralize(text, tags) {
        return collapseSpaces(tags ? text : text.replaceAll("[", "(").replaceAll("]", ")"));
    }

    function splitParts(text) {
        return text
            .split(LINE_BREAK)
            .map((line) => line.replace(EDGE_SPACE, ""))
            .filter((line) => line !== "");
    }

    function validatePart(text, tags) {
        const spoken = neutralize(text, tags);
        if (!spoken || spoken === LINE_SEPARATOR || spoken.toLowerCase().includes("<break")) {
            throw new Error("a line cannot be empty, a lone “…” or contain a <break> tag");
        }
    }

    function documentText(parts, tags) {
        return parts.map((part) => neutralize(part, tags)).join(PART_GLUE) + "\n";
    }

    function timeline(chunks) {
        const text = chunks.flatMap((chunk) => chunk.chars).join("");
        const starts = chunks.flatMap((chunk) => chunk.startsMs.map((start) => chunk.offsetMs + start));
        const ends = chunks.flatMap((chunk) =>
            chunk.startsMs.map((start, index) => chunk.offsetMs + start + chunk.durationsMs[index]),
        );
        const silent = chunks.flatMap((chunk) => chunk.chars.map(() => chunk.silent));
        return { text, starts, ends, silent };
    }

    function segment(codePoints, first, stop) {
        let last = stop - 1;
        while (first <= last && isSpace(codePoints[first])) first += 1;
        while (last >= first && isSpace(codePoints[last])) last -= 1;
        if (first > last || codePoints.slice(first, last + 1).join("") === LINE_SEPARATOR) return null;
        return [first, last];
    }

    function partSpans(chunks, parts, tags) {
        const { text, starts, ends, silent } = timeline(chunks);
        const codePoints = Array.from(text);
        const bounds = [];
        let cursor = 0;
        for (const match of [...codePointMatches(BREAK_RUN, text), null]) {
            const bound = segment(codePoints, cursor, match === null ? codePoints.length : match[0]);
            if (bound !== null) bounds.push(bound);
            cursor = match === null ? codePoints.length : match[1];
        }
        if (bounds.length !== parts.length) {
            throw new Error(`ElevenReader line count mismatch: received ${bounds.length}, expected ${parts.length}`);
        }
        return parts.map((part, line) => {
            const [first, last] = bounds[line];
            if (codePoints.slice(first, last + 1).join("") !== neutralize(part, tags)) {
                throw new Error(`ElevenReader line text mismatch at line ${line + 1}`);
            }
            if (ends[last] < starts[first]) throw new Error(`ElevenReader part timing is reversed at line ${line + 1}`);
            const unspoken = silent.slice(first, last + 1).some(Boolean);
            return { start_ms: starts[first], end_ms: unspoken ? starts[first] : ends[last] };
        });
    }

    // ── Subtitles (port of src/timestamps.py) ────────────────────────────────────

    function splitWords(text, starts, ends) {
        const codePoints = Array.from(text);
        const inBreak = new Array(codePoints.length).fill(false);
        for (const [start, end] of codePointMatches(BREAK_TAG, text)) inBreak.fill(true, start, end);
        const tokens = [];
        let wordStart = null;
        for (let k = 0; k <= codePoints.length; k += 1) {
            const boundary = k === codePoints.length || inBreak[k] || isSpace(codePoints[k]);
            if (boundary && wordStart !== null) {
                tokens.push({ text: codePoints.slice(wordStart, k).join(""), start_ms: starts[wordStart], end_ms: ends[k - 1] });
                wordStart = null;
            }
            if (k < codePoints.length && inBreak[k] && (tokens.length === 0 || tokens[tokens.length - 1] !== null)) {
                tokens.push(null);
            }
            if (!boundary && wordStart === null) wordStart = k;
        }
        return tokens;
    }

    function endsSentence(word) {
        const codePoints = Array.from(word.text);
        while (codePoints.length && CLOSING_MARKS.includes(codePoints[codePoints.length - 1])) codePoints.pop();
        return codePoints.length === 0 || SENTENCE_END.includes(codePoints[codePoints.length - 1]);
    }

    function startsSentence(word) {
        const codePoints = Array.from(word.text);
        if (DASHES.includes(codePoints[0])) return false;
        const letter = codePoints.find((char) => /\p{L}/u.test(char));
        return letter === undefined || !/\p{Lowercase}/u.test(letter);
    }

    function splitSentences(text, starts, ends) {
        const sentences = [];
        let current = [];
        for (const token of splitWords(text, starts, ends)) {
            const newSentence =
                token === null || (current.length > 0 && endsSentence(current[current.length - 1]) && startsSentence(token));
            if (newSentence && current.length) {
                sentences.push(current);
                current = [];
            }
            if (token !== null) current.push(token);
        }
        if (current.length) sentences.push(current);
        return sentences;
    }

    function srtTime(ms) {
        const total = pyRound(ms);
        const pad = (value, width) => String(value).padStart(width, "0");
        const hours = Math.floor(total / 3600000);
        const minutes = Math.floor((total % 3600000) / 60000);
        const seconds = Math.floor((total % 60000) / 1000);
        return `${pad(hours, 2)}:${pad(minutes, 2)}:${pad(seconds, 2)},${pad(total % 1000, 3)}`;
    }

    function srtText(sentences) {
        return sentences
            .map((words, index) => {
                const text = words.map((word) => word.text).join(" ");
                return `${index + 1}\n${srtTime(words[0].start_ms)} --> ${srtTime(words[words.length - 1].end_ms)}\n${text}\n`;
            })
            .join("\n");
    }

    // ── Result files ─────────────────────────────────────────────────────────────

    function resultFiles(name, { voice, durationMs, chunks, parts, tags }) {
        const { text, starts, ends } = timeline(chunks);
        const entries =
            parts === null
                ? []
                : partSpans(chunks, parts, tags).map((span, index) => ({
                      index,
                      text: parts[index],
                      start_ms: span.start_ms,
                      end_ms: span.end_ms,
                      spoken: span.end_ms > span.start_ms,
                  }));
        const json = {
            audio: `${name}.mp3`,
            voice,
            duration_ms: durationMs,
            parts: entries,
            words: splitWords(text, starts, ends).filter((word) => word !== null),
            silent: entries.filter((entry) => !entry.spoken).map((entry) => entry.index),
        };
        return { json, srt: srtText(splitSentences(text, starts, ends)) };
    }

    function readIdFromStreamUrl(url) {
        const path = new URL(url).pathname;
        const at = path.indexOf(STREAM_PATH);
        if (at < 0) return null;
        const readId = path.slice(at + STREAM_PATH.length).split("/")[0];
        return readId ? decodeURIComponent(readId) : null;
    }

    function voiceFromUrl(url) {
        const voice = VOICES.find((candidate) => url.includes(candidate.voice_id));
        return voice === undefined ? null : voice.alias;
    }

    function fileStem(name) {
        const stem = name
            .replace(/[\\/:*?"<>|\x00-\x1f]+/g, "_")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 120);
        return stem || "edp";
    }

    // ── Account (port of engine/api_backend.py) ──────────────────────────────────

    function accountSettings(config) {
        const voice = config.default_voice_id;
        const speed = config.playback_speed_rate;
        return { voice_id: typeof voice === "string" ? voice : null, speed: isNumber(speed) ? speed : null };
    }

    function withSettings(config, voiceId, speed) {
        const updated = { ...config };
        if (voiceId !== null) updated.default_voice_id = voiceId;
        if (speed !== null) updated.playback_speed_rate = speed;
        return updated;
    }

    function httpError(status, action) {
        if (status === 401) return new Error(`ElevenReader rejected the session during ${action}; sign in again`);
        if (status === 403) return new Error(`ElevenReader refused access to the account during ${action}`);
        if (status === 402) return new Error(`ElevenReader account has no credits left (${action})`);
        if (status === 429) return new Error(`ElevenReader rate limit reached during ${action}`);
        return new Error(`ElevenReader API failed during ${action} (HTTP ${status})`);
    }

    function readIdOf(body) {
        const value = isObject(body) ? body.read_id : undefined;
        if (typeof value === "string" && value) return value;
        return isNumber(value) ? String(value) : null;
    }

    // ── Page hooks ───────────────────────────────────────────────────────────────

    function installSocketHook(win, onStream, onError) {
        const NativeWebSocket = win.WebSocket;
        if (typeof NativeWebSocket !== "function") {
            onError(new Error("window.WebSocket is missing; the stream cannot be recorded"));
            return false;
        }
        class WebSocket extends NativeWebSocket {
            constructor(...args) {
                super(...args);
                try {
                    if (String(this.url).includes(STREAM_PATH)) onStream(this, String(this.url));
                } catch (error) {
                    onError(error);
                }
            }
        }
        win.WebSocket = WebSocket;
        return true;
    }

    function attachRecorder(socket, recorder, { onSent, onChange, onError }) {
        socket.addEventListener("message", (event) => {
            try {
                recorder.onFrame(event.data);
            } catch (error) {
                onError(error);
            }
            onChange();
        });
        const nativeSend = socket.send;
        socket.send = function (data) {
            try {
                recorder.onSent(data);
                onSent(data);
            } catch (error) {
                onError(error);
            }
            return nativeSend.call(this, data);
        };
    }

    function installSpeedHook(win, onError) {
        const playing = new Set();
        const patched = new Set();
        let speed = 1;
        const apply = (source, rate) => {
            try {
                source.playbackRate.value = rate;
            } catch (error) {
                onError(error);
            }
        };
        for (const Context of [win.AudioContext, win.webkitAudioContext]) {
            if (typeof Context !== "function" || patched.has(Context.prototype)) continue;
            patched.add(Context.prototype);
            const originalCreate = Context.prototype.createBufferSource;
            Context.prototype.createBufferSource = function () {
                const source = originalCreate.call(this);
                const originalStart = source.start;
                source.start = function (...args) {
                    if (speed !== 1) apply(source, speed);
                    playing.add(source);
                    source.addEventListener("ended", () => playing.delete(source));
                    return originalStart.apply(this, args);
                };
                return source;
            };
        }
        return (next) => {
            speed = next;
            for (const source of playing) apply(source, next);
        };
    }

    function requestInfo(input, init) {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : String(input.url);
        const headers = new Headers(typeof input === "object" && "headers" in input ? input.headers : undefined);
        if (init && init.headers) new Headers(init.headers).forEach((value, key) => headers.set(key, value));
        const method = String((init && init.method) || (typeof input === "object" && input.method) || "GET").toUpperCase();
        return { url, method, authorization: headers.get("authorization") };
    }

    function installRequestHooks(win, { onRequest, onAddReply, onError }) {
        const nativeFetch = win.fetch;
        win.fetch = function (input, init) {
            let info = null;
            try {
                info = requestInfo(input, init);
                onRequest(info);
            } catch (error) {
                onError(error);
            }
            const reply = nativeFetch.apply(win, arguments);
            if (info !== null && info.method === "POST" && info.url.includes(ADD_ENDPOINT)) {
                reply
                    .then((response) =>
                        response
                            .clone()
                            .json()
                            .then((body) => onAddReply(response.status, body)),
                    )
                    .catch(onError);
            }
            return reply;
        };
        const requests = new WeakMap();
        const XHR = win.XMLHttpRequest.prototype;
        const nativeOpen = XHR.open;
        const nativeSetHeader = XHR.setRequestHeader;
        XHR.open = function (method, url, ...rest) {
            requests.set(this, { method: String(method).toUpperCase(), url: String(url) });
            return nativeOpen.call(this, method, url, ...rest);
        };
        XHR.setRequestHeader = function (name, value) {
            const request = requests.get(this);
            if (request && String(name).toLowerCase() === "authorization") {
                onRequest({ url: request.url, method: request.method, authorization: String(value) });
            }
            return nativeSetHeader.call(this, name, value);
        };
        const nativeSend = XHR.send;
        XHR.send = function (...args) {
            const request = requests.get(this);
            if (request && request.method === "POST" && request.url.includes(ADD_ENDPOINT)) {
                this.addEventListener("loadend", () => {
                    try {
                        const body = this.responseType === "json" ? this.response : JSON.parse(this.responseText);
                        onAddReply(this.status, body);
                    } catch (error) {
                        onError(error);
                    }
                });
            }
            return nativeSend.apply(this, args);
        };
        return nativeFetch.bind(win);
    }

    // ── Browser app ──────────────────────────────────────────────────────────────

    function start(win) {
        const doc = win.document;
        const state = {
            recording: null,
            job: null,
            token: null,
            busy: false,
            messages: [],
            v2: false,
            addWaiter: null,
        };
        let panel = null;
        let renderTimer = null;

        const report = (level, message, error) => {
            const text = error === undefined ? message : `${message}: ${error && error.message ? error.message : error}`;
            if (level === "error") console.error("[EDP]", text, error ?? "");
            else console.warn("[EDP]", text);
            state.messages.push({ level, text });
            if (state.messages.length > 12) state.messages.shift();
            render();
        };
        const fail = (error) => report("error", "unexpected failure", error);

        const storage = (kind) => {
            try {
                return win[kind];
            } catch (error) {
                report("error", `${kind} is not available`, error);
                return null;
            }
        };
        const readStored = (kind, key) => {
            const store = storage(kind);
            if (store === null) return null;
            try {
                const raw = store.getItem(key);
                return raw === null ? null : JSON.parse(raw);
            } catch (error) {
                report("error", `stored ${key} is unreadable`, error);
                return null;
            }
        };
        const writeStored = (kind, key, value) => {
            const store = storage(kind);
            if (store === null) return;
            try {
                if (value === null) store.removeItem(key);
                else store.setItem(key, JSON.stringify(value));
            } catch (error) {
                report("error", `could not store ${key}`, error);
            }
        };
        const loadCleanup = () => {
            const stored = readStored("localStorage", CLEANUP_KEY);
            return {
                restore: isObject(stored) && isObject(stored.restore) ? stored.restore : null,
                reads: isObject(stored) && Array.isArray(stored.reads) ? stored.reads.filter((id) => typeof id === "string") : [],
            };
        };
        const saveCleanup = (cleanup) =>
            writeStored("localStorage", CLEANUP_KEY, cleanup.restore === null && !cleanup.reads.length ? null : cleanup);

        const guard = (what, install, fallback) => {
            try {
                return install();
            } catch (error) {
                report("error", `${what} could not be installed`, error);
                return fallback;
            }
        };
        guard("stream hook", () => installSocketHook(win, onStream, (error) => report("error", "stream hook failed", error)), false);
        const setPageSpeed = guard(
            "page speed hook",
            () => installSpeedHook(win, (error) => report("error", "page speed could not be set", error)),
            () => {},
        );
        const nativeFetch = guard(
            "request hook",
            () =>
                installRequestHooks(win, {
                    onRequest: (info) => {
                        if (info.authorization && info.url.includes(API_HOST)) state.token = info.authorization;
                    },
                    onAddReply: (status, body) => {
                        if (state.addWaiter !== null) state.addWaiter(status, body);
                    },
                    onError: (error) => report("error", "page request could not be inspected", error),
                }),
            win.fetch.bind(win),
        );

        async function api(method, url, action, body) {
            if (!state.token) throw new Error("no ElevenReader token seen yet; wait until the page has loaded your library");
            const headers = { authorization: state.token };
            if (body !== undefined) headers["content-type"] = "application/json";
            const response = await nativeFetch(url, {
                method,
                headers,
                body: body === undefined ? undefined : JSON.stringify(body),
                signal: AbortSignal.timeout(ACTION_TIMEOUT_S * 1000),
            });
            if (!response.ok && !(method === "DELETE" && response.status === 404)) throw httpError(response.status, action);
            if (method !== "GET") return null;
            const json = await response.json();
            if (!isObject(json)) throw new Error(`ElevenReader returned no object during ${action}`);
            return json;
        }

        async function prepareAccount(voiceId, cleanup) {
            const current = await api("GET", USER_CONFIG_URL, "read_account");
            if (cleanup.restore === null) {
                cleanup.restore = accountSettings(current);
                saveCleanup(cleanup);
            }
            await api("POST", USER_CONFIG_URL, "set_account", withSettings(current, voiceId, READING_SPEED));
            const check = accountSettings(await api("GET", USER_CONFIG_URL, "check_account"));
            if (check.voice_id !== voiceId || check.speed !== READING_SPEED) {
                throw new Error("ElevenReader account did not take the voice or reading speed");
            }
        }

        async function cleanAccount(restore) {
            const cleanup = loadCleanup();
            const step = async (kind, work) => {
                try {
                    await Promise.race([
                        work(),
                        new Promise((_, reject) =>
                            setTimeout(() => reject(new Error("timed out")), CLEANUP_STEP_TIMEOUT_S * 1000),
                        ),
                    ]);
                    return true;
                } catch (error) {
                    report("error", `account cleanup step ${kind} failed and stays pending`, error);
                    return false;
                }
            };
            if (restore && cleanup.restore !== null) {
                const settings = cleanup.restore;
                const restored = await step("restore_settings", async () => {
                    const current = await api("GET", USER_CONFIG_URL, "read_account");
                    await api("POST", USER_CONFIG_URL, "restore_account", withSettings(current, settings.voice_id, settings.speed));
                });
                if (restored) cleanup.restore = null;
            }
            for (const readId of [...cleanup.reads]) {
                const deleted = await step("delete_read", () => api("DELETE", `${READS_URL}/${readId}`, "delete_read"));
                if (deleted) cleanup.reads = cleanup.reads.filter((id) => id !== readId);
            }
            saveCleanup(cleanup);
            render();
        }

        function newRecording(readId) {
            const recorder = new StreamRecorder((level, message) => report(level, message));
            return { readId, recorder, voices: [], saved: false, failed: null };
        }

        function onStream(socket, url) {
            const readId = readIdFromStreamUrl(url);
            const previous = state.recording;
            if (previous === null || previous.readId !== readId || previous.saved || previous.recorder.stopped) {
                if (previous !== null && !previous.saved && previous.failed === null && previous.recorder.audioBytes) {
                    report("warning", "a new stream started; saving the unfinished recording first");
                    save(previous);
                }
                state.recording = newRecording(readId);
            }
            const recording = state.recording;
            recording.voices.push(voiceFromUrl(url));
            attachRecorder(socket, recording.recorder, {
                onSent: (data) => onSent(recording, data),
                onChange: () => onChange(recording),
                onError: (error) => report("error", "stream frame could not be recorded", error),
            });
            socket.addEventListener("close", () => render());
            setPageSpeed(PAGE_SPEED);
            render();
        }

        function onSent(recording, data) {
            const position = sentPosition(data);
            if (position !== null && position > 0 && recording.recorder.chars === 0) {
                report("warning", `the page started reading at character ${position}, not at the beginning; rewind and reload`);
            }
            if (isV2Speed(recording.recorder.listeningSpeed) && !recording.recorder.stopped) {
                recording.recorder.stop();
                state.v2 = true;
                setPageSpeed(1);
                failRecording(recording, "model v2: the account reading speed must be 1x; set it and reload the document");
            }
        }

        function onChange(recording) {
            if (recording.recorder.final && !recording.recorder.stopped) {
                recording.recorder.stop();
                setPageSpeed(1);
                finish(recording);
            }
            render();
        }

        function finish(recording) {
            const job = state.job;
            if (job !== null && job.readId === recording.readId) {
                const problem =
                    recording.recorder.chars < job.charCount
                        ? `recording is incomplete: received ${recording.recorder.chars} of ${job.charCount} characters`
                        : recording.voices.some((voice) => voice === job.voice)
                          ? null
                          : "the stream address did not carry the selected voice";
                if (problem !== null) {
                    failRecording(recording, problem);
                    return;
                }
                save(recording);
                endJob();
                return;
            }
            save(recording);
        }

        function failRecording(recording, message) {
            recording.failed = message;
            report("error", message);
            if (state.job !== null && state.job.readId === recording.readId) endJob();
        }

        function save(recording) {
            const job = state.job !== null && state.job.readId === recording.readId ? state.job : null;
            const name = fileStem(job ? job.name : panel ? panel.name.value || doc.title : doc.title);
            const voice = job ? job.voice : (recording.voices.find((alias) => alias !== null) ?? null);
            const recorder = recording.recorder;
            const result = { voice, durationMs: recorder.offsetMs, chunks: recorder.chunks, parts: job ? job.parts : null };
            let files;
            try {
                files = resultFiles(name, { ...result, tags: job ? job.tags : false });
            } catch (error) {
                report("error", "part timings could not be matched; saving without parts", error);
                files = resultFiles(name, { ...result, parts: null, tags: false });
            }
            download(doc, `${name}.mp3`, new Blob(recorder.audio, { type: "audio/mpeg" }));
            download(doc, `${name}.json`, new Blob([JSON.stringify(files.json, null, 2) + "\n"], { type: "application/json" }));
            download(doc, `${name}.srt`, new Blob([files.srt], { type: "application/x-subrip" }));
            recording.saved = true;
            for (const index of files.json.silent) report("warning", `line ${index + 1} was not spoken by the server`);
            render();
        }

        function endJob() {
            const job = state.job;
            state.job = null;
            writeStored("sessionStorage", JOB_KEY, null);
            if (job !== null) cleanAccount(true).catch(fail);
        }

        async function recordText(text, voiceAlias, tags, name) {
            const parts = splitParts(text);
            if (!parts.length) throw new Error("paste some text first");
            parts.forEach((part, index) => {
                try {
                    validatePart(part, tags);
                } catch (error) {
                    throw new Error(`line ${index + 1}: ${error.message}`);
                }
            });
            const uploaded = documentText(parts, tags);
            if (Array.from(uploaded).length > MAX_DOCUMENT_CHARS) {
                throw new Error(`the text exceeds ${MAX_DOCUMENT_CHARS} characters; split it into smaller pieces`);
            }
            const voice = VOICES.find((candidate) => candidate.alias === voiceAlias);
            if (!state.token) throw new Error("no ElevenReader token seen yet; wait until the library has loaded");
            const importButton = findButton(doc, "Import");
            if (importButton === null) throw new Error(`open ${LIBRARY_URL} to upload text`);
            const cleanup = loadCleanup();
            try {
                const { readId, charCount } = await upload(importButton, uploaded, cleanup);
                await prepareAccount(voice.voice_id, cleanup);
                const job = { readId, charCount, parts, tags, voice: voice.alias, name: name || "edp" };
                writeStored("sessionStorage", JOB_KEY, job);
                win.location.assign(`${LIBRARY_URL}/${readId}`);
            } catch (error) {
                await cleanAccount(true);
                throw error;
            }
        }

        async function upload(importButton, text, cleanup) {
            let timer = null;
            const reply = new Promise((resolve, reject) => {
                timer = setTimeout(
                    () => reject(new Error("ElevenReader did not answer the upload; the document may stay in your library")),
                    ACTION_TIMEOUT_S * 1000,
                );
                state.addWaiter = (status, body) => resolve({ status, body });
            });
            try {
                importButton.click();
                const input = await waitFor(() => doc.querySelector("input[type=file]"), ACTION_TIMEOUT_S, "file input");
                const transfer = new DataTransfer();
                transfer.items.add(new File([text], DOCUMENT_NAME, { type: "text/plain" }));
                input.files = transfer.files;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                const uploadButton = await waitFor(() => findButton(doc, "Upload"), ACTION_TIMEOUT_S, "Upload button");
                uploadButton.click();
                const { status, body } = await reply;
                if (status < 200 || status >= 300) throw httpError(status, "upload");
                const readId = readIdOf(body);
                if (readId === null) {
                    throw new Error("ElevenReader upload reply lacked the read id; the document may stay in your library");
                }
                cleanup.reads.push(readId);
                saveCleanup(cleanup);
                const charCount = isObject(body) ? body.char_count : undefined;
                if (!Number.isInteger(charCount) || charCount <= 0) {
                    throw new Error("ElevenReader upload reply lacked the document length");
                }
                return { readId, charCount };
            } finally {
                clearTimeout(timer);
                state.addWaiter = null;
            }
        }

        function resumeJob() {
            const job = readStored("sessionStorage", JOB_KEY);
            if (!isObject(job) || typeof job.readId !== "string") return;
            if (!win.location.pathname.endsWith(`/${job.readId}`)) {
                writeStored("sessionStorage", JOB_KEY, null);
                report("warning", "a pasted-text recording was interrupted by leaving its document; press “Clean up account now”");
                return;
            }
            state.job = job;
        }

        function watchJob() {
            const job = state.job;
            const startedAt = Date.now();
            let playedAt = null;
            let plays = 0;
            let lastBytes = 0;
            let lastProgress = Date.now();
            const timer = setInterval(() => {
                if (state.job !== job) {
                    clearInterval(timer);
                    return;
                }
                const recording = state.recording;
                const now = Date.now();
                if (playedAt === null) {
                    const play = findButton(doc, "Play");
                    if (play !== null) {
                        setPageSpeed(PAGE_SPEED);
                        play.click();
                        playedAt = now;
                        plays = 1;
                    } else if (now - startedAt >= READY_TIMEOUT_S * 1000) {
                        stopJob("the document never became playable");
                    }
                    return;
                }
                setPageSpeed(PAGE_SPEED);
                if (recording === null || !recording.recorder.audioBytes) {
                    if (now - playedAt < START_TIMEOUT_S * 1000) return;
                    if (plays >= PLAY_ATTEMPTS) {
                        stopJob("ElevenReader sent no audio after Play");
                        return;
                    }
                    const play = findButton(doc, "Play");
                    if (play !== null) play.click();
                    plays += 1;
                    playedAt = now;
                    return;
                }
                if (recording.recorder.audioBytes !== lastBytes) {
                    lastBytes = recording.recorder.audioBytes;
                    lastProgress = now;
                }
                if (now - lastProgress >= STALL_S * 1000) stopJob("ElevenReader recording stalled");
            }, POLL_S * 1000);
        }

        function stopJob(message) {
            const recording = state.recording;
            if (recording !== null && state.job !== null && recording.readId === state.job.readId) {
                recording.recorder.stop();
                setPageSpeed(1);
                failRecording(recording, message);
                return;
            }
            report("error", message);
            endJob();
        }

        async function setSpeedOne() {
            const current = await api("GET", USER_CONFIG_URL, "read_account");
            await api("POST", USER_CONFIG_URL, "set_account", withSettings(current, null, READING_SPEED));
            state.v2 = false;
            report("warning", "account reading speed set to 1x; reload the document to record with model v4");
        }

        function run(work) {
            if (state.busy) return;
            state.busy = true;
            render();
            work()
                .catch((error) => report("error", "action failed", error))
                .finally(() => {
                    state.busy = false;
                    render();
                });
        }

        function render() {
            if (panel === null || renderTimer !== null) return;
            renderTimer = setTimeout(() => {
                renderTimer = null;
                updatePanel(panel, state, loadCleanup());
                if (!panel.root.isConnected) doc.body.appendChild(panel.root);
            }, 200);
        }

        resumeJob();
        const mount = () => {
            panel = createPanel(doc, {
                save: () => (state.recording !== null && state.recording.recorder.audioBytes ? save(state.recording) : report("warning", "nothing recorded yet")),
                speedOne: () => run(setSpeedOne),
                cleanUp: () => run(() => cleanAccount(true)),
                cancel: () => stopJob("cancelled"),
                record: (text, voice, tags, name) => run(() => recordText(text, voice, tags, name)),
            });
            doc.body.appendChild(panel.root);
            render();
            if (state.job !== null) watchJob();
        };
        if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", mount, { once: true });
        else mount();
    }

    function findButton(doc, name) {
        for (const element of doc.querySelectorAll("button, [role=button]")) {
            const label = (element.getAttribute("aria-label") ?? element.textContent ?? "").trim();
            if (label === name && element.getClientRects().length > 0 && !element.closest("#edp-panel")) return element;
        }
        return null;
    }

    function waitFor(find, timeoutS, what) {
        return new Promise((resolve, reject) => {
            const startedAt = Date.now();
            const timer = setInterval(() => {
                const found = find();
                if (found !== null) {
                    clearInterval(timer);
                    resolve(found);
                } else if (Date.now() - startedAt >= timeoutS * 1000) {
                    clearInterval(timer);
                    reject(new Error(`the page did not show the ${what}`));
                }
            }, 250);
        });
    }

    function download(doc, fileName, blob) {
        const url = URL.createObjectURL(blob);
        const link = doc.createElement("a");
        link.href = url;
        link.download = fileName;
        link.style.display = "none";
        doc.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    // ── Panel ────────────────────────────────────────────────────────────────────

    function element(doc, tag, style, text) {
        const node = doc.createElement(tag);
        Object.assign(node.style, style);
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function createPanel(doc, actions) {
        const root = element(doc, "div", {
            position: "fixed",
            top: "16px",
            right: "16px",
            width: "300px",
            zIndex: "2147483647",
            background: "#16161e",
            color: "#e6e6ef",
            font: "12px/1.4 system-ui, sans-serif",
            border: "1px solid #44445a",
            borderRadius: "10px",
            boxShadow: "0 8px 24px rgba(0,0,0,.5)",
            overflow: "hidden",
        });
        root.id = "edp-panel";
        const header = element(doc, "div", { padding: "8px 10px", background: "#22222e", cursor: "move", fontWeight: "700" }, `EDP ${VERSION}`);
        const body = element(doc, "div", { padding: "10px", display: "grid", gap: "6px" });
        const status = element(doc, "div", { fontWeight: "600" });
        const stats = element(doc, "div", { color: "#a8a8c0" });
        const messages = element(doc, "div", { display: "grid", gap: "2px", maxHeight: "140px", overflowY: "auto" });
        const button = (label, onClick) => {
            const node = element(
                doc,
                "button",
                { padding: "6px 8px", border: "0", borderRadius: "6px", background: "#5b4bd6", color: "#fff", cursor: "pointer", font: "inherit" },
                label,
            );
            node.type = "button";
            node.addEventListener("click", onClick);
            return node;
        };
        const field = (tag, style) => {
            const node = element(doc, tag, { background: "#0e0e14", color: "inherit", border: "1px solid #44445a", borderRadius: "6px", padding: "5px", font: "inherit", ...style });
            return node;
        };
        const name = field("input", {});
        name.placeholder = "file name (default: page title)";
        const save = button("Save recording now", actions.save);
        const speedOne = button("Set account speed 1x", actions.speedOne);
        const cleanUp = button("Clean up account now", actions.cleanUp);
        const cancel = button("Cancel pasted-text recording", actions.cancel);

        const textBox = field("textarea", { height: "90px", resize: "vertical" });
        textBox.placeholder = "Paste text: every non-empty line is one paragraph";
        const voice = field("select", {});
        for (const option of VOICES) {
            const node = doc.createElement("option");
            node.value = option.alias;
            node.textContent = option.label;
            voice.appendChild(node);
        }
        const tagsLabel = element(doc, "label", { display: "flex", gap: "6px", alignItems: "center" });
        const tags = doc.createElement("input");
        tags.type = "checkbox";
        tagsLabel.append(tags, doc.createTextNode("Pass v4 [tags] to the server"));
        const record = button("Upload and record text", () => actions.record(textBox.value, voice.value, tags.checked, name.value));
        const pasted = element(doc, "div", { display: "grid", gap: "6px", borderTop: "1px solid #44445a", paddingTop: "8px" });
        pasted.append(textBox, voice, tagsLabel, record);

        body.append(status, stats, messages, name, save, speedOne, cleanUp, cancel, pasted);
        root.append(header, body);

        let drag = null;
        const move = (event) => {
            root.style.left = `${event.clientX - drag.x}px`;
            root.style.top = `${event.clientY - drag.y}px`;
            root.style.right = "auto";
        };
        const stop = () => {
            doc.removeEventListener("mousemove", move);
            doc.removeEventListener("mouseup", stop);
            drag = null;
        };
        header.addEventListener("mousedown", (event) => {
            const box = root.getBoundingClientRect();
            drag = { x: event.clientX - box.left, y: event.clientY - box.top };
            doc.addEventListener("mousemove", move);
            doc.addEventListener("mouseup", stop);
            event.preventDefault();
        });

        return { root, status, stats, messages, name, save, speedOne, cleanUp, cancel, record, pasted, doc };
    }

    function updatePanel(panel, state, cleanup) {
        const recording = state.recording;
        const recorder = recording === null ? null : recording.recorder;
        let status = "Waiting for a document stream";
        if (recording !== null) {
            if (recording.failed !== null) status = "Recording failed";
            else if (recording.saved) status = "Saved";
            else if (recorder.final) status = "Finished";
            else status = state.job !== null ? "Recording pasted text" : "Recording the open document";
        } else if (state.job !== null) status = "Waiting for the pasted-text document to play";
        panel.status.textContent = status;
        panel.stats.textContent =
            recorder === null
                ? state.token
                    ? "Signed-in page detected"
                    : "No account token seen yet"
                : `${recorder.chars} characters · ${(recorder.offsetMs / 60000).toFixed(1)} min · ${(recorder.audioBytes / 1048576).toFixed(2)} MB`;
        panel.messages.replaceChildren(
            ...state.messages.map((message) =>
                element(panel.doc, "div", { color: message.level === "error" ? "#ff7a8a" : "#ffc861" }, message.text),
            ),
        );
        const pending = cleanup.restore !== null || cleanup.reads.length > 0;
        panel.speedOne.style.display = state.v2 ? "" : "none";
        panel.cleanUp.style.display = pending && state.job === null ? "" : "none";
        panel.cancel.style.display = state.job !== null ? "" : "none";
        panel.pasted.style.display = state.job !== null ? "none" : "grid";
        for (const node of [panel.save, panel.speedOne, panel.cleanUp, panel.record]) node.disabled = state.busy;
    }

    // ── Entry ────────────────────────────────────────────────────────────────────

    if (typeof window === "object" && window !== null && window.document) start(window);

    if (typeof module === "object" && module !== null && module.exports) {
        module.exports = {
            VOICES,
            PAGE_SPEED,
            StreamRecorder,
            attachRecorder,
            installSocketHook,
            isV2Speed,
            framesDurationMs,
            cutBeforeMs,
            pySum,
            pyRound,
            neutralize,
            splitParts,
            validatePart,
            documentText,
            partSpans,
            splitWords,
            splitSentences,
            srtTime,
            srtText,
            resultFiles,
            readIdFromStreamUrl,
            voiceFromUrl,
            sentPosition,
            accountSettings,
            withSettings,
        };
    }
})();
