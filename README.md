# 🎧 Eleven Downloader Pro

A powerful Tampermonkey userscript that allows you to download audio directly from **ElevenReader** and **ElevenLabs**. It intercepts WebSocket traffic to capture high-quality audio buffers before they play, enabling features like 16x speed recording and automatic file merging.

## ✨ Features

- **Audio Interception:** Captures raw audio data directly from the server (WebSocket/AudioContext) bypassing CORS restrictions.
- **Turbo Mode (16x):** Forces the playback engine to 16x speed to "drain" the audio buffer and record hours of content in minutes.
- **Passive Mode:** Listen normally without recording.
- **Smart RAM Management:** Tracks memory usage and automatically downloads/clears buffer when it hits 1GB to prevent browser crashes.
- **Auto-Save:** Automatically downloads the file after a set period of silence (configurable via slider).
- **Modern UI:** Draggable, dark-themed interface with precise controls.

## 🚀 Installation

1. Install the **Tampermonkey** extension for your browser (Chrome, Edge, Firefox).
2. Click on the extension icon and select **"Create a new script"**.
3. Delete any default code and paste the content of `script.js` from this repository.
4. Press **Ctrl+S** (File -> Save).
5. Go to [ElevenReader](https://elevenreader.io) or [ElevenLabs](https://elevenlabs.io).

## 🎮 Usage

1. **Open the Panel:** Reload the page and you will see the "Eleven Downloader" panel in the top-right corner.
2. **Start Recording:**
   - Click **RECORD**. The status will change to `RECORDING (16x)`.
   - Click **Play** on the website's text player. The audio will play at high speed (muted) to accelerate capturing.
3. **Finish & Download:**
   - Wait for the text to finish.
   - If **Auto-Download** is active, it will save automatically after the silence timer runs out.
   - Manually click **DOWNLOAD** to save the `.mp3` file immediately.
4. **Passive Mode:** Click **PASSIVE MODE** if you just want to listen to the text normally without recording.

## Python tools in `src/` (recommended)

Measurements, limits and what the recorded data can be used for are described in [docs/report.md](docs/report.md) and [docs/research/capabilities.md](docs/research/capabilities.md). Which markup tags work in ElevenReader: [docs/research/elevenreader-tags.md](docs/research/elevenreader-tags.md).

`src/downloader.py` (manual) and `src/auto.py` (automatic) launch your installed Google Chrome with its own profile and writes the audio straight to disk while recording. There is no RAM limit and no silence timer, which split the files in the userscript.

### Installation

Requires [uv](https://docs.astral.sh/uv/) and Google Chrome. `uv run` creates the `.venv` environment and installs the dependencies on first use, so there is no manual setup.

### Running

```bash
uv run src/downloader.py --url "https://elevenreader.io/reader/library/u:YOUR_DOCUMENT"
```

- Without a file name the recording goes to the first free `workspace/output/recording_N.mp3`.
- With a name, e.g. `uv run src/downloader.py workspace/output/book.mp3 --url "..."`, it writes to that file. An existing file is **appended to**, which is how you finish a recording after a break.
- `--speed 16` changes the speed-up (default 64).
- `--chrome "C:\...\chrome.exe"` sets the path when Chrome is installed in a non-standard location.

### Usage

1. Run the script. The first time, sign in inside the opened Chrome (the session is kept in `.chrome-profile/`).
2. Open the document and move to its beginning. Nothing is recorded at start and the page plays at normal speed.
3. **Click the terminal window and press SPACE.** It prints `RECORDING (64.0x)`.
4. Press **play** in Chrome.
5. When `saved X MB` stops growing and the player reaches the end, press **Ctrl+C** in the terminal.

Keys work while the terminal window is focused:

| Key    | Action                                                    |
| ------ | --------------------------------------------------------- |
| Space  | record / pause                                            |
| C      | clear the file (e.g. when unwanted audio got in at start) |
| Ctrl+C | quit                                                      |

### Automatic mode: `auto.py`

Converts every document in `workspace/input/` without any clicking:

```bash
uv run src/auto.py
```

For each `.txt`, `.md`, `.epub`, `.pdf`, `.docx`, `.doc` or `.html` file it imports the file into your ElevenReader library, sets the account's ElevenReader reading speed to 1x, opens the new document (it always starts at the beginning), records it at `--speed` (default 64) until the player reaches the end, and saves `workspace/output/<name>.mp3` with its text in `<name>.txt`. Finished inputs move to `workspace/input/done/`.

The reading speed decides the voice model: at 1x the server reads with Eleven v4, at about 3x with the older v2. The page starts its stream at the account speed as soon as a document opens, and the server keeps the model for the whole stream, so `auto.py` sets 1x through the account settings before it opens a document. The log shows the speed of every stream (`reading speed 1x: Eleven v4`); a stream at any other speed stops the recording at once and the input goes to `failed/`. `downloader.py` prints a `WARNING` instead: set the reading speed to 1x in the player and reopen the document.

| Option         | Effect                                                                     |
| -------------- | -------------------------------------------------------------------------- |
| `--parallel N` | records N documents at once, each in its own tab (measured: 3 = 3x faster) |
| `--headless`   | runs Chrome without a window                                               |
| `--speed X`    | playback speed in the page while recording (default 64)                    |

After each file the log prints `text received: X/Y chars`, where Y is the length the server reported at upload. Equal numbers mean the whole document was recorded; fewer marks the file `INCOMPLETE`, more prints a `WARNING` about a possible repeated sentence. Every 10 s a status line shows the saved size, the audio throughput and whether the speed-up is active (`speed 64x ok`); a missing or overridden speed-up is fixed on the fly and reported as `FIXED`.

If ElevenReader is down (e.g. 502 Bad Gateway), the run waits and retries every minute for up to 2 hours. If no new audio arrives for 5 minutes before the end, the input moves to `workspace/input/failed/` and the log prints the `downloader.py` command that resumes it by hand. `downloader.py` stays the manual fallback.

### Timestamps

The server sends a start time and duration for every character with the audio. Both scripts store them and, when a recording ends, write next to `<name>.mp3`:

| File                 | Contents                                                           |
| -------------------- | ------------------------------------------------------------------ |
| `<name>.srt`         | subtitles, one logical sentence per entry                          |
| `<name>.json`        | sentences with start/end in seconds and the timing of every word   |
| `<name>.txt`         | the plain text the server read                                     |
| `<name>.align.jsonl` | raw per-chunk character timings, the source for `.srt` and `.json` |

Sentences end at `.`, `!`, `?` or `…` when the next word starts a new sentence (a dash or a lowercase word continues it, as in `“Who?” he asked.`) and at every pause ElevenReader inserts between paragraphs. Times stay correct when a recording is appended to. To rebuild the subtitles from the raw timings:

```bash
uv run src/timestamps.py workspace/output/book.align.jsonl
```

### Voice-over clips: `clips.py`

Turns a subtitle file into one audio clip per line, e.g. for a voice-over track:

```bash
uv run src/clips.py prepare episode.srt                # writes workspace/input/episode.txt, one line per paragraph
uv run src/auto.py                                      # records it
uv run src/clips.py cut workspace/output/episode.align.jsonl episode.srt
uv run src/clips.py verify workspace/output/episode_clips
```

`cut` finds every subtitle line in the recording and writes `NNN.mp3`, `NNN.txt` and `manifest.json` (subtitle times, audio times, durations) to `workspace/output/<name>_clips/`. Every subtitle gets its own clip. The server's character timings run about 0.3 s ahead of the audio, so `cut` decodes the recording and places every cut in the silence between two lines (`--no-snap` cuts by the timings alone).

Where the narrator reads two lines without a pause, there is no silence to cut in. `cut` then places the boundary at its share of the character timings between the silences around that stretch of speech and cuts at the quietest 50 ms within 200 ms of it. Such a cut can still move a short word into the neighbouring clip, so `cut` lists these lines (`cut without silence`); check them by ear.

`verify` decodes each clip and flags edges at speech level.

### Folder layout

```text
workspace/
  input/    documents for auto.py (done/ and failed/ are created when needed)
  output/   finished recordings: .mp3, .srt, .json, .txt, .align.jsonl
```

The contents of `workspace/` are ignored by git; only the folders are kept (`.gitkeep`).

### Good to know

- The server sends audio in batches, sometimes large ones at once. `next chunk arrived after X s` only means waiting; nothing is missing in the file.
- When the terminal is quiet but the page keeps playing, the page is playing audio that is already in the file. Wait: when the player reaches the end of its buffer, the server sends the next part.
- Do not click in the document text while recording; a jump records a different place. Press SPACE (pause) first.
- Identical repeated chunks are skipped (`skipped duplicate chunk`).
- The server sends the text with the audio: the terminal shows it live and the whole text goes to a `.txt` file next to the `.mp3`.
- In manual mode use one Chrome and one document tab at a time, otherwise the audio gets mixed. Each run works in its own new tab and closes it at the end; `auto.py --parallel` keeps every document in a separate tab.
- Speed: one session receives audio at about 4.5–5.5x real time (measured 2026-10-17/18), whatever the page playback speed above 16x; parallel sessions add up (2 sessions ≈ 11x, 3 ≈ 17x in total). On 2026-10-19 this stopped being reliable: opening a new stream closed an older one, with 4 tabs and with 2 (all tabs share one device). Record one file at a time (the default) unless a parallel run is checked file by file. At 64x the page player may hang just before the end; `auto.py` then finishes once the whole text has arrived or the player is within 30 characters of the end. If a recording ever lands in `failed/` with all its audio, use `--speed 16`.
- Usage is counted in characters, including the pauses the server inserts between paragraphs: 1 ElevenReader credit per 10,000 characters regardless of speed. Recording exactly the same text again with the same voice is served from the server's cache: about 58x real time and no credits used.

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Please respect ElevenLabs' Terms of Service and usage limits. I am not responsible for any banned accounts or misused data.
