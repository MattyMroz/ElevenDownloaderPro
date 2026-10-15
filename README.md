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

## 🐍 Wersja Python: `downloader.py` (zalecana)

Uruchamia Twojego Google Chrome (osobny profil) i zapisuje audio prosto na dysk w trakcie nagrywania. Nie ma limitu RAM-u ani timera ciszy, który dzielił pliki w userscripcie.

### Instalacja

```
pip install playwright
```

Wymaga zainstalowanego Google Chrome.

### Uruchomienie

```
python downloader.py --url "https://elevenreader.io/reader/library/u:TWOJ_DOKUMENT"
```

* Bez nazwy pliku nagranie trafia do pierwszego wolnego `nagranie_1.mp3`, `nagranie_2.mp3`, ...
* Z nazwą, np. `python downloader.py ksiazka.mp3 --url "..."`, zapisuje do `ksiazka.mp3`. Jeśli plik istnieje, **dopisuje na końcu**. Tak dogrywasz resztę po przerwie.
* `--speed 32` zmienia przyspieszenie (domyślnie 16).
* `--chrome "C:\...\chrome.exe"` podaje ścieżkę, jeśli Chrome jest w nietypowym miejscu.

### Jak używać

1. Uruchom skrypt. Za pierwszym razem zaloguj się w otwartym Chrome (sesja zapisuje się w `.chrome-profile/`).
2. Wejdź w dokument i przewiń na początek. Na starcie nic się nie nagrywa, strona gra normalnie.
3. **Kliknij w okno terminala i wciśnij SPACJĘ.** Pojawi się `NAGRYWAM (16.0x)`.
4. Kliknij **play** w Chrome.
5. Gdy `zapisano X MB` przestanie rosnąć, a odtwarzacz dojdzie do końca, wciśnij **Ctrl+C** w terminalu.

Klawisze (działają, gdy aktywne jest okno terminala):

| Klawisz | Działanie |
|---|---|
| Spacja | nagrywaj / pauza |
| C | wyczyść plik (np. gdy na początek wpadło coś zbędnego) |
| Ctrl+C | koniec |

### Dobrze wiedzieć

* Serwer wysyła audio paczkami, czasem dużymi porcjami naraz. Komunikat `serwer wysłał następną paczkę po X s` to tylko czekanie, w pliku nic nie brakuje.
* Kiedy terminal stoi, a strona dalej gra, strona odtwarza to, co już jest w pliku. Czekaj: gdy odtwarzacz dojdzie do końca bufora, serwer przyśle kolejną część.
* Podczas nagrywania nie klikaj w tekst dokumentu. Przeskok nagra inne miejsce. Najpierw wciśnij spację (pauza).
* Identyczne powtórzone paczki są pomijane (`pominięto powtórzony fragment`).
* Jeśli serwer wysyła tekst razem z audio, terminal pokazuje go na bieżąco, a całość trafia do pliku `.txt` obok `.mp3`.
* Jeden Chrome, jedna karta z dokumentem naraz. Inaczej audio się wymiesza.

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Please respect ElevenLabs' Terms of Service and usage limits. I am not responsible for any banned accounts or misused data.