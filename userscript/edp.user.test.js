"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { describe, test } = require("node:test");

const edp = require("./edp.user.js");

const FIXTURES = path.join(__dirname, "..", "tests", "fixtures");
const FRAME_HEADER = [0xff, 0xfb, 0x90, 0x64];
const FRAME_BYTES = 417;
const FRAME_MS = (1152 * 1000) / 44100;
const BREAK = '<break time="0.6s"/>';
const FIRST = "The quick brown fox jumps over";
const CONFIG = JSON.stringify({ type: "config" });
const STREAM_URL = "wss://api.elevenlabs.io/v1/reader/reads/stream/v2/u:read42?voice_id=T5l58N8RNz5DKoClpKIJ";

function mp3Frames(count, fill = 0) {
    const frame = [...FRAME_HEADER, ...new Array(FRAME_BYTES - FRAME_HEADER.length).fill(fill)];
    return Buffer.from(Array.from({ length: count }, () => frame).flat());
}

function audioFrame(chars, { frames = 4, fill = 0, stepMs = 10.0, key = "alignment" } = {}) {
    const payload = { audio: mp3Frames(frames, fill).toString("base64") };
    if (chars) {
        const letters = Array.from(chars);
        payload[key] = {
            chars: letters,
            charStartTimesMs: letters.map((_, index) => index * stepMs),
            charDurationsMs: letters.map(() => stepMs),
        };
    }
    return JSON.stringify(payload);
}

function recorder() {
    const issues = [];
    return { recorder: new edp.StreamRecorder((level, message) => issues.push({ level, message })), issues };
}

function recorded(rec) {
    return Buffer.concat(rec.audio.map((chunk) => Buffer.from(chunk)));
}

function chunk(text, { offsetMs = 0.0, stepMs = 10.0, silent = false } = {}) {
    const chars = Array.from(text);
    return {
        offsetMs,
        chars,
        startsMs: chars.map((_, index) => index * stepMs),
        durationsMs: chars.map(() => stepMs),
        silent,
    };
}

function spans(chunks, ...parts) {
    return edp.partSpans(chunks, parts, false).map((span) => [span.start_ms, span.end_ms]);
}

function readFixture(name) {
    return fs.readFileSync(path.join(FIXTURES, name), "utf8");
}

function recordFixture(name) {
    const { recorder: rec, issues } = recorder();
    for (const line of readFixture(`${name}.frames.jsonl`).split("\n").filter(Boolean)) rec.onFrame(line);
    return { rec, issues };
}

class FakeSocket extends EventTarget {
    static CONNECTING = 0;
    static OPEN = 1;

    constructor(url) {
        super();
        this.url = url;
        this.sent = [];
    }

    send(data) {
        this.sent.push(data);
    }
}

function hookedWindow(onRecorder) {
    const win = { WebSocket: FakeSocket };
    const errors = [];
    edp.installSocketHook(
        win,
        (socket) => {
            const rec = new edp.StreamRecorder();
            onRecorder(rec);
            edp.attachRecorder(socket, rec, { onSent: () => {}, onChange: () => {}, onError: (error) => errors.push(error) });
        },
        (error) => errors.push(error),
    );
    return { win, errors };
}

describe("stream hook", () => {
    test("regression #1: audio sent right after the stream opens, before any user action, is recorded", () => {
        const recorders = [];
        const { win, errors } = hookedWindow((rec) => recorders.push(rec));

        const socket = new win.WebSocket(STREAM_URL);
        socket.dispatchEvent(new MessageEvent("message", { data: audioFrame("Ab", { frames: 3 }) }));

        assert.equal(recorders.length, 1);
        assert.deepEqual(recorded(recorders[0]), mp3Frames(3));
        assert.equal(recorders[0].chars, 2);
        assert.equal(recorders[0].chunks[0].offsetMs, 0.0);
        assert.deepEqual(errors, []);
    });

    test("hooked constructor keeps instanceof, static fields and the native send", () => {
        const { win } = hookedWindow(() => {});

        const socket = new win.WebSocket(STREAM_URL);
        socket.send(JSON.stringify({ listening_speed: 1 }));

        assert.ok(socket instanceof FakeSocket);
        assert.ok(socket instanceof win.WebSocket);
        assert.equal(win.WebSocket.OPEN, 1);
        assert.equal(win.WebSocket.name, "WebSocket");
        assert.deepEqual(socket.sent, [JSON.stringify({ listening_speed: 1 })]);
    });

    test("socket outside the read stream path gets no recorder", () => {
        const recorders = [];
        const { win } = hookedWindow((rec) => recorders.push(rec));

        new win.WebSocket("wss://api.elevenlabs.io/v1/other");

        assert.equal(recorders.length, 0);
    });

    test("sent listening speed reaches the recorder through the hooked send", () => {
        const recorders = [];
        const { win } = hookedWindow((rec) => recorders.push(rec));

        new win.WebSocket(STREAM_URL).send(JSON.stringify({ listening_speed: 3.1 }));

        assert.equal(recorders[0].listeningSpeed, 3.1);
        assert.ok(edp.isV2Speed(recorders[0].listeningSpeed));
    });

    test("stream url gives the read id and the voice alias", () => {
        assert.equal(edp.readIdFromStreamUrl(STREAM_URL), "u:read42");
        assert.equal(edp.voiceFromUrl(STREAM_URL), "fronczewski");
        assert.equal(edp.voiceFromUrl("wss://api.elevenlabs.io/v1/reader/reads/stream/v2/u:x"), null);
    });
});

describe("recorder", () => {
    test("audio with alignment writes audio and timings", () => {
        const { recorder: rec } = recorder();

        rec.onFrame(audioFrame("Ab", { frames: 3 }));

        assert.deepEqual(recorded(rec), mp3Frames(3));
        assert.equal(rec.audioBytes, 3 * FRAME_BYTES);
        assert.equal(rec.chars, 2);
        assert.deepEqual(rec.chunks[0].chars, ["A", "b"]);
        assert.deepEqual(rec.chunks[0].startsMs, [0.0, 10.0]);
    });

    test("second chunk offset is the first chunk duration", () => {
        const { recorder: rec } = recorder();

        rec.onFrame(audioFrame("Ab", { frames: 3, fill: 1 }));
        rec.onFrame(audioFrame("Cd", { frames: 2, fill: 2 }));

        assert.ok(Math.abs(rec.chunks[1].offsetMs - 3 * FRAME_MS) < 1e-9);
    });

    test("large duplicate chunk is skipped", () => {
        const { recorder: rec } = recorder();
        const frame = audioFrame("Ab", { frames: 20 });

        rec.onFrame(frame);
        rec.onFrame(frame);

        assert.equal(rec.audioBytes, 20 * FRAME_BYTES);
        assert.equal(rec.chars, 2);
    });

    test("small duplicate chunk is kept", () => {
        const { recorder: rec } = recorder();
        const frame = audioFrame("", { frames: 2 });

        rec.onFrame(frame);
        rec.onFrame(frame);

        assert.equal(rec.audioBytes, 4 * FRAME_BYTES);
    });

    test("chunk without alignment keeps audio and advances the offset", () => {
        const { recorder: rec } = recorder();

        rec.onFrame(audioFrame("", { frames: 2 }));
        rec.onFrame(audioFrame("Xy", { frames: 1 }));

        assert.equal(rec.chars, 2);
        assert.equal(rec.chunks.length, 1);
        assert.ok(Math.abs(rec.chunks[0].offsetMs - 2 * FRAME_MS) < 1e-9);
    });

    test("normalized alignment is used when alignment is missing", () => {
        const { recorder: rec } = recorder();

        rec.onFrame(audioFrame("Ab", { frames: 1, key: "normalizedAlignment" }));

        assert.equal(rec.chars, 2);
    });

    test("partial repeat after reconnect is trimmed together with its audio", () => {
        const { recorder: rec } = recorder();
        rec.onFrame(audioFrame(FIRST, { frames: 12, fill: 1 }));

        rec.onFrame(CONFIG);
        rec.onFrame(audioFrame("brown fox jumps over the lazy dog", { frames: 12, fill: 2 }));

        assert.equal(rec.chars, FIRST.length + " the lazy dog".length);
        assert.equal(rec.chunks.at(-1).chars.join(""), " the lazy dog");
        assert.ok(Math.abs(rec.chunks.at(-1).startsMs[0]) < 1e-9);
        assert.equal(rec.audioBytes, 12 * FRAME_BYTES + 4 * FRAME_BYTES);
    });

    test("full repeat after reconnect is skipped", () => {
        const { recorder: rec } = recorder();
        rec.onFrame(audioFrame(FIRST, { frames: 12, fill: 1 }));

        rec.onFrame(CONFIG);
        rec.onFrame(audioFrame("fox jumps over", { frames: 5, fill: 2 }));

        assert.equal(rec.chars, FIRST.length);
        assert.equal(rec.audioBytes, 12 * FRAME_BYTES);
    });

    test("anchored repeat continues across chunks after reconnect", () => {
        const { recorder: rec } = recorder();
        rec.onFrame(audioFrame(FIRST, { frames: 12, fill: 1 }));

        rec.onFrame(CONFIG);
        rec.onFrame(audioFrame("quick brown fox", { frames: 5, fill: 2 }));
        rec.onFrame(audioFrame(" jumps over and on", { frames: 9, fill: 3 }));

        assert.equal(rec.chars, FIRST.length + " and on".length);
        assert.equal(rec.chunks.at(-1).chars.join(""), " and on");
    });

    test("text without a reconnect is never trimmed", () => {
        const { recorder: rec } = recorder();
        rec.onFrame(audioFrame(FIRST, { frames: 12, fill: 1 }));

        rec.onFrame(audioFrame("brown fox jumps over", { frames: 5, fill: 2 }));

        assert.equal(rec.chars, FIRST.length + "brown fox jumps over".length);
    });

    for (const [label, payload] of [
        ["binary", new Uint8Array([1, 2])],
        ["not json", "not json"],
        ["json array", "[1, 2]"],
        ["undecodable audio", JSON.stringify({ audio: "!!!" })],
    ]) {
        test(`unusable payload (${label}) writes nothing and reports an error`, () => {
            const { recorder: rec, issues } = recorder();

            rec.onFrame(payload);

            assert.equal(rec.audioBytes, 0);
            assert.equal(rec.chars, 0);
            assert.equal(issues.length, 1);
            assert.equal(issues[0].level, "error");
        });
    }

    test("empty object frame writes nothing and reports nothing", () => {
        const { recorder: rec, issues } = recorder();

        rec.onFrame("{}");

        assert.equal(rec.audioBytes, 0);
        assert.deepEqual(issues, []);
    });

    test("final frame marks the recording finished", () => {
        const { recorder: rec } = recorder();

        rec.onFrame(audioFrame("Ab", { frames: 1 }));
        rec.onFrame(JSON.stringify({ isFinal: true }));

        assert.equal(rec.final, true);
        assert.equal(rec.chars, 2);
    });

    test("stopped recorder ignores later frames", () => {
        const { recorder: rec } = recorder();

        rec.stop();
        rec.onFrame(audioFrame("Ab", { frames: 1 }));
        rec.onSent(JSON.stringify({ listening_speed: 3.0 }));

        assert.equal(rec.audioBytes, 0);
        assert.equal(rec.listeningSpeed, null);
    });

    for (const [chars, frames, silent] of [
        ["x".repeat(20), 1, true],
        ["x".repeat(20), 7, true],
        ["x".repeat(20), 8, false],
        ["x".repeat(20), 16, false],
        ["x".repeat(19), 1, false],
        ["x".repeat(19) + BREAK, 1, false],
        ["x y ".repeat(10) + BREAK, 1, true],
    ]) {
        test(`chunk of ${chars.length} chars in ${frames} frames is silent: ${silent}`, () => {
            const { recorder: rec, issues } = recorder();

            rec.onFrame(audioFrame(chars, { frames, stepMs: 1.0 }));

            assert.equal(rec.chunks[0].silent, silent);
            assert.equal(rec.chars, chars.length);
            assert.equal(issues.filter((issue) => issue.level === "warning").length, silent ? 1 : 0);
        });
    }
});

describe("model v2 detection", () => {
    for (const [payload, expected] of [
        [{ listening_speed: 1 }, false],
        [{ listening_speed: 3.0 }, true],
        [{ listening_speed: 2.65 }, true],
    ]) {
        test(`sent listening speed ${payload.listening_speed} is v2: ${expected}`, () => {
            const { recorder: rec } = recorder();

            rec.onSent(JSON.stringify(payload));

            assert.equal(rec.listeningSpeed, payload.listening_speed);
            assert.equal(edp.isV2Speed(rec.listeningSpeed), expected);
        });
    }

    for (const payload of ["{}", JSON.stringify({ listening_speed: true }), "nope", new Uint8Array([0])]) {
        test(`sent frame without a numeric speed (${String(payload)}) keeps v2 undecided`, () => {
            const { recorder: rec } = recorder();

            rec.onSent(payload);

            assert.equal(rec.listeningSpeed, null);
            assert.equal(edp.isV2Speed(rec.listeningSpeed), false);
        });
    }

    test("sent position is read only from a numeric position field", () => {
        assert.equal(edp.sentPosition(JSON.stringify({ position: 149, listening_speed: 1 })), 149);
        assert.equal(edp.sentPosition(JSON.stringify({ listening_position: 149 })), null);
        assert.equal(edp.sentPosition("nope"), null);
    });
});

describe("document", () => {
    for (const [text, expected] of [
        ["[śmiech] No [pewnie]", "(śmiech) No (pewnie)"],
        ["Dwie\n linie\t i  spacje ", "Dwie linie i spacje"],
        ["Bez zmian: „cudzysłów”…", "Bez zmian: „cudzysłów”…"],
    ]) {
        test(`document text of ${JSON.stringify(text)} has round brackets and single spaces`, () => {
            assert.equal(edp.documentText([text], false), `${expected}\n`);
        });
    }

    test("document text puts a separator paragraph between parts", () => {
        assert.equal(edp.documentText(["Raz [dwa].", "Trzy\ncztery."], false), "Raz (dwa).\n\n…\n\nTrzy cztery.\n");
    });

    test("document text with v4 tags keeps square brackets", () => {
        assert.equal(edp.documentText(["[laughs] Raz."], true), "[laughs] Raz.\n");
    });

    test("pasted text splits into trimmed non-empty lines", () => {
        assert.deepEqual(edp.splitParts(" Raz. \r\n\n  \nDwa.\u2028Trzy."), ["Raz.", "Dwa.", "Trzy."]);
    });

    for (const text of ["   ", "…", 'Ab <break time="1s"/> cd', "<BREAK/>"]) {
        test(`part ${JSON.stringify(text)} is refused`, () => {
            assert.throws(() => edp.validatePart(text, false));
            assert.throws(() => edp.validatePart(text, true));
        });
    }
});

describe("part spans", () => {
    test("break tags split parts in server time", () => {
        assert.deepEqual(spans([chunk('Ab. <break time="0.6s"/> Cd.')], "Ab.", "Cd."), [
            [0.0, 30.0],
            [250.0, 280.0],
        ]);
    });

    test("separator paragraph is not a part", () => {
        assert.deepEqual(spans([chunk('Ab. <break time="0.6s"/> … <break time="0.6s"/> Cd.')], "Ab.", "Cd."), [
            [0.0, 30.0],
            [480.0, 510.0],
        ]);
    });

    test("adjacent break tags form one boundary", () => {
        assert.deepEqual(spans([chunk('Ab.<break time="0.6s"/> <break time="0.6s"/>Cd.')], "Ab.", "Cd."), [
            [0.0, 30.0],
            [440.0, 470.0],
        ]);
    });

    test("part the server did not speak returns an empty span", () => {
        const unspoken = { offsetMs: 250.0, chars: ["j", " ", "g"], startsMs: [0, 0, 0], durationsMs: [0, 0, 0], silent: false };
        const chunks = [chunk('Ab. <break time="0.6s"/> '), unspoken, chunk(' <break time="0.6s"/> Cd.', { offsetMs: 300.0 })];

        assert.deepEqual(spans(chunks, "Ab.", "j g", "Cd."), [
            [0.0, 30.0],
            [250.0, 250.0],
            [520.0, 550.0],
        ]);
    });

    test("parts touching a silent chunk return empty spans", () => {
        const chunks = [
            chunk('Ab. <break time="0.6s"/> C'),
            chunk('d. <break time="0.6s"/> Ef.', { offsetMs: 300.0, stepMs: 1.0, silent: true }),
            chunk(' <break time="0.6s"/> Gh.', { offsetMs: 330.0 }),
        ];

        const result = spans(chunks, "Ab.", "Cd.", "Ef.", "Gh.");

        assert.deepEqual(
            result.map(([start, end]) => end > start),
            [true, false, false, true],
        );
        assert.deepEqual(result[3], [550.0, 580.0]);
    });

    test("ellipsis ending a part stays in its text", () => {
        const chunks = [chunk('Zobacz filmik… <break time="0.6s"/> … <break time="0.6s"/> Cd.')];

        assert.deepEqual(spans(chunks, "Zobacz filmik…", "Cd."), [
            [0.0, 140.0],
            [590.0, 620.0],
        ]);
    });

    test("final break adds no empty part", () => {
        assert.equal(spans([chunk('Ab. <break time="0.6s"/> Cd. <break time="2s"/>')], "Ab.", "Cd.").length, 2);
    });

    test("tag cut between chunks still splits", () => {
        const chunks = [chunk("Ab. <break ti"), chunk('me="0.6s"/> Cd.', { offsetMs: 1000.0 })];

        assert.deepEqual(spans(chunks, "Ab.", "Cd."), [
            [0.0, 30.0],
            [1120.0, 1150.0],
        ]);
    });

    test("unclosed tag at the end is dropped", () => {
        assert.deepEqual(spans([chunk('Ab. <break time="2')], "Ab."), [[0.0, 30.0]]);
    });

    test("part ending before it starts throws", () => {
        const reversed = { offsetMs: 0, chars: ["A", "b", "."], startsMs: [100, 50, 0], durationsMs: [10, 10, 10], silent: false };

        assert.throws(() => edp.partSpans([reversed], ["Ab."], false), /timing is reversed/);
    });

    test("surrounding whitespace is trimmed", () => {
        assert.deepEqual(spans([chunk("  Ab  ")], "Ab"), [[20.0, 40.0]]);
    });

    test("bracketed part matches round brackets in server text", () => {
        assert.deepEqual(spans([chunk("(Ab)")], "[Ab]"), [[0.0, 40.0]]);
    });

    test("bracketed part with v4 tags matches square brackets in server text", () => {
        assert.deepEqual(
            edp.partSpans([chunk("[Ab]")], ["[Ab]"], true).map((span) => [span.start_ms, span.end_ms]),
            [[0.0, 40.0]],
        );
    });

    test("line count mismatch throws", () => {
        assert.throws(() => spans([chunk('Ab. <break time="0.6s"/> Cd.')], "Ab. Cd."), /line count mismatch/);
    });

    test("line text mismatch throws", () => {
        assert.throws(() => spans([chunk('Ab. <break time="0.6s"/> Cd.')], "Ab.", "Ef."), /line text mismatch/);
    });

    test("no chunks and no parts return nothing", () => {
        assert.deepEqual(edp.partSpans([], [], false), []);
    });
});

describe("subtitles", () => {
    test("srt time rounds half to even like Python", () => {
        assert.equal(edp.srtTime(500.5), "00:00:00,500");
        assert.equal(edp.srtTime(501.5), "00:00:00,502");
        assert.equal(edp.srtTime(3723004.4), "01:02:03,004");
    });

    test("frame durations use compensated summation like Python sum", () => {
        assert.equal(edp.pySum([0.1, 0.2, 0.3]), 0.6);
        assert.equal(edp.framesDurationMs(mp3Frames(10)), edp.pySum(new Array(10).fill(FRAME_MS)));
    });

    test("break tag closes a sentence even without punctuation", () => {
        const text = `Rozdział 1 ${BREAK} Początek.`;
        const times = Array.from(text, (_, index) => index * 10);

        const sentences = edp.splitSentences(text, times, times);

        assert.deepEqual(
            sentences.map((words) => words.map((word) => word.text).join(" ")),
            ["Rozdział 1", "Początek."],
        );
    });

    test("dash or lowercase start continues the sentence", () => {
        const text = "Dobrze. — powiedział. np. coś. Koniec.";
        const times = Array.from(text, (_, index) => index * 10);

        const sentences = edp.splitSentences(text, times, times);

        assert.deepEqual(
            sentences.map((words) => words.map((word) => word.text).join(" ")),
            ["Dobrze. — powiedział. np. coś.", "Koniec."],
        );
    });
});

describe("words and subtitles of known parts", () => {
    function files(chunks, parts) {
        return edp.resultFiles("x", { voice: null, durationMs: 0, chunks, parts, tags: false });
    }

    test("separator paragraph never becomes a word or a subtitle", () => {
        const { json, srt } = files([chunk('Ab. <break time="0.6s"/> … <break time="0.6s"/> Cd. <break time="2s"/>')], ["Ab.", "Cd."]);

        assert.deepEqual(
            json.words.map((word) => word.text),
            ["Ab.", "Cd."],
        );
        assert.ok(!srt.includes("…"));
        assert.equal(srt.split(" --> ").length - 1, 2);
    });

    test("ellipsis ending a part stays in its word", () => {
        const { json } = files([chunk('Zobacz filmik… <break time="0.6s"/> … <break time="0.6s"/> Cd.')], ["Zobacz filmik…", "Cd."]);

        assert.deepEqual(
            json.words.map((word) => word.text),
            ["Zobacz", "filmik…", "Cd."],
        );
    });

    test("sentence ends at the end of its part", () => {
        const { srt } = files([chunk('Ab <break time="0.6s"/> … <break time="0.6s"/> cd')], ["Ab", "cd"]);

        assert.equal(srt, "1\n00:00:00,000 --> 00:00:00,020\nAb\n\n2\n00:00:00,470 --> 00:00:00,490\ncd\n");
    });

    test("words of an unspoken part are left out", () => {
        const chunks = [
            chunk('Ab. <break time="0.6s"/> C'),
            chunk('d. <break time="0.6s"/> Ef.', { offsetMs: 300.0, stepMs: 1.0, silent: true }),
            chunk(' <break time="0.6s"/> Gh.', { offsetMs: 330.0 }),
        ];

        const { json } = files(chunks, ["Ab.", "Cd.", "Ef.", "Gh."]);

        assert.deepEqual(
            json.words.map((word) => word.text),
            ["Ab.", "Gh."],
        );
        assert.deepEqual(json.silent, [1, 2]);
    });

    test("open document without parts keeps the separator like src/timestamps.py", () => {
        const { json } = files([chunk('Ab. <break time="0.6s"/> … <break time="0.6s"/> Cd.')], null);

        assert.deepEqual(
            json.words.map((word) => word.text),
            ["Ab.", "…", "Cd."],
        );
    });
});

describe("fixtures from Python", () => {
    for (const [name, parts] of [
        ["open-document", null],
        ["pasted-text", edp.splitParts(readFixture("pasted-text.txt"))],
    ]) {
        test(`${name} frames give the srt computed by Python`, () => {
            const { rec } = recordFixture(name);

            const { srt } = edp.resultFiles(name, { voice: null, durationMs: rec.offsetMs, chunks: rec.chunks, parts, tags: false });

            assert.equal(srt, readFixture(`${name}.srt`));
        });
    }

    test("open-document frames give the json computed by Python", () => {
        const { rec, issues } = recordFixture("open-document");

        const { json } = edp.resultFiles("open-document", {
            voice: null,
            durationMs: rec.offsetMs,
            chunks: rec.chunks,
            parts: null,
            tags: false,
        });

        assert.equal(rec.final, true);
        assert.deepEqual(issues, []);
        assert.deepEqual(json, JSON.parse(readFixture("open-document.json")));
    });

    test("pasted-text frames give the json with part timings and the silent line", () => {
        const { rec, issues } = recordFixture("pasted-text");
        const parts = edp.splitParts(readFixture("pasted-text.txt"));

        const { json } = edp.resultFiles("pasted-text", {
            voice: "fronczewski",
            durationMs: rec.offsetMs,
            chunks: rec.chunks,
            parts,
            tags: false,
        });

        assert.deepEqual(json, JSON.parse(readFixture("pasted-text.json")));
        assert.deepEqual(json.silent, [2]);
        assert.deepEqual(
            issues.map((issue) => issue.level),
            ["warning"],
        );
    });
});
