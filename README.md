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

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Please respect ElevenLabs' Terms of Service and usage limits. I am not responsible for any banned accounts or misused data.