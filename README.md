# 🎧 Eleven Downloader Pro 

A powerful Tampermonkey userscript that allows you to download audio directly from **ElevenReader** and **ElevenLabs**. It intercepts WebSocket traffic to capture high-quality audio buffers before they play, enabling features like 16x speed recording and automatic file merging.

## ✨ Features

*   **Audio Interception:** Captures raw audio data directly from the server (WebSocket/AudioContext) bypassing CORS restrictions.
*   **Turbo Mode (16x):** Forces the playback engine to 16x speed to "drain" the audio buffer and record hours of content in minutes.
*   **Passive Mode:** Listen normally without recording.
*   **Smart RAM Management:** Tracks memory usage and automatically downloads/clears buffer when it hits 1GB to prevent browser crashes.
*   **Auto-Save:** Automatically downloads the file after a set period of silence (configurable via slider).
*   **Modern UI:** Draggable, dark-themed interface with precise controls.

## 🚀 Installation

1.  Install the **Tampermonkey** extension for your browser (Chrome, Edge, Firefox).
2.  Click on the extension icon and select **"Create a new script"**.
3.  Delete any default code and paste the content of `script.js` from this repository.
4.  Press **Ctrl+S** (File -> Save).
5.  Go to [ElevenReader](https://elevenreader.io) or [ElevenLabs](https://elevenlabs.io).

## 🎮 Usage

1.  **Open the Panel:** Reload the page and you will see the "Eleven Downloader" panel in the top-right corner.
2.  **Start Recording:**
    *   Click **RECORD**. The status will change to `RECORDING (16x)`.
    *   Click **Play** on the website's text player. The audio will play at high speed (muted) to accelerate capturing.
3.  **Finish & Download:**
    *   Wait for the text to finish.
    *   If **Auto-Download** is active, it will save automatically after the silence timer runs out.
    *   Manually click **DOWNLOAD** to save the `.mp3` file immediately.
4.  **Passive Mode:** Click **PASSIVE MODE** if you just want to listen to the text normally without recording.

## Python version: `downloader.py` (recommended)

Launches your installed Google Chrome with its own profile and writes the audio straight to disk while recording. There is no RAM limit and no silence timer, which split the files in the userscript.

### Installation

Requires [uv](https://docs.astral.sh/uv/) and Google Chrome. `uv run` creates the `.venv` environment and installs the dependencies on first use, so there is no manual setup.

### Running

```bash
uv run downloader.py --url "https://elevenreader.io/reader/library/u:YOUR_DOCUMENT"
```

- Without a file name the recording goes to the first free `workspace/output/recording_N.mp3`.
- With a name, e.g. `uv run downloader.py workspace/output/book.mp3 --url "..."`, it writes to that file. An existing file is **appended to**, which is how you finish a recording after a break.
- `--speed 32` changes the speed-up (default 16).
- `--chrome "C:\...\chrome.exe"` sets the path when Chrome is installed in a non-standard location.

### Usage

1. Run the script. The first time, sign in inside the opened Chrome (the session is kept in `.chrome-profile/`).
2. Open the document and move to its beginning. Nothing is recorded at start and the page plays at normal speed.
3. **Click the terminal window and press SPACE.** It prints `RECORDING (16.0x)`.
4. Press **play** in Chrome.
5. When `saved X MB` stops growing and the player reaches the end, press **Ctrl+C** in the terminal.

Keys work while the terminal window is focused:

| Key    | Action                                                    |
| ------ | --------------------------------------------------------- |
| Space  | record / pause                                            |
| C      | clear the file (e.g. when unwanted audio got in at start) |
| Ctrl+C | quit                                                      |

### Folder layout

```text
workspace/
  input/    input files (e.g. .txt for future automation)
  output/   finished .mp3 recordings and their .txt text
```

The contents of `workspace/` are ignored by git; only the folders are kept (`.gitkeep`).

### Good to know

- The server sends audio in batches, sometimes large ones at once. `next chunk arrived after X s` only means waiting; nothing is missing in the file.
- When the terminal is quiet but the page keeps playing, the page is playing audio that is already in the file. Wait: when the player reaches the end of its buffer, the server sends the next part.
- Do not click in the document text while recording; a jump records a different place. Press SPACE (pause) first.
- Identical repeated chunks are skipped (`skipped duplicate chunk`).
- The server sends the text with the audio: the terminal shows it live and the whole text goes to a `.txt` file next to the `.mp3`.
- One Chrome and one document tab at a time, otherwise the audio gets mixed.

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Please respect ElevenLabs' Terms of Service and usage limits. I am not responsible for any banned accounts or misused data.