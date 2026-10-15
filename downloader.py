"""Eleven Downloader Pro - wersja Python (Playwright).

Uruchamia zwykłego Google Chrome (osobny profil) i podłącza się do niego,
żeby działało logowanie przez Google. Startuje w trybie pasywnym (bez
nagrywania, normalna prędkość). W terminalu: SPACJA włącza/pauzuje
nagrywanie z przyspieszeniem, C czyści plik. Każda próbka audio z WebSocketu
trafia od razu na dysk, więc przerwanie nie gubi danych.

Instalacja:
    pip install playwright
    (wymaga zainstalowanego Google Chrome)

Użycie:
    python downloader.py [plik.mp3] [--speed 16] [--url https://elevenreader.io/] [--chrome ŚCIEŻKA]
    Bez nazwy pliku zapisuje do pierwszego wolnego nagranie_1.mp3, nagranie_2.mp3, ...

Zatrzymanie: Ctrl+C albo zamknięcie okna przeglądarki.
Ponowne uruchomienie z tą samą nazwą pliku dopisuje audio na końcu.
"""
import argparse
import base64
import hashlib
import json
import msvcrt
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

PROFILE_DIR = Path(__file__).with_name('.chrome-profile')
CDP_PORT = 9222
CHROME_PATHS = [
    Path(os.environ.get('PROGRAMFILES', r'C:\Program Files'), r'Google\Chrome\Application\chrome.exe'),
    Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), r'Google\Chrome\Application\chrome.exe'),
    Path(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
]

SPEED_JS = """
(() => {
    window.__edpSpeed = 1;
    for (const Ctx of [window.AudioContext, window.webkitAudioContext]) {
        if (!Ctx) continue;
        const originalCreate = Ctx.prototype.createBufferSource;
        Ctx.prototype.createBufferSource = function () {
            const src = originalCreate.call(this);
            const origStart = src.start;
            src.start = function () {
                if (window.__edpSpeed !== 1) {
                    try { src.playbackRate.value = window.__edpSpeed; } catch (e) {}
                }
                return origStart.apply(this, arguments);
            };
            return src;
        };
    }
})();
"""


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


class Recorder:
    def __init__(self, out, transcript):
        self.out = out
        self.transcript = transcript
        self.warned_no_text = False
        self.total = 0
        self.last_audio_at = None
        self.recording = False
        self.seen = set()

    def on_websocket(self, ws):
        log(f'WS open {ws.url}')
        ws.on('framereceived', self.on_frame)
        ws.on('close', lambda _: log(f'WS close {ws.url}'))
        ws.on('socketerror', lambda err: log(f'WS error {err}'))

    def on_frame(self, payload):
        if not self.recording:
            return
        if isinstance(payload, bytes):
            log(f'wiadomość binarna, {len(payload)} B')
            return
        try:
            data = json.loads(payload)
        except ValueError:
            log(f'wiadomość nie-JSON: {payload[:300]}')
            return
        if not isinstance(data, dict):
            return

        audio = data.pop('audio', None)
        if audio:
            chunk = base64.b64decode(audio)
            digest = hashlib.sha1(chunk).digest()
            if digest in self.seen:
                log(f'pominięto powtórzony fragment ({len(chunk)} B)')
                return
            self.seen.add(digest)
            self.out.write(chunk)
            self.out.flush()
            self.total += len(chunk)
            alignment = data.get('alignment') or data.get('normalizedAlignment') or {}
            text = ''.join(alignment.get('chars') or [])
            if text:
                self.transcript.write(text)
                self.transcript.flush()
                log(f'+ {" ".join(text.split())[:100]}')
            elif not self.warned_no_text:
                self.warned_no_text = True
                log(f'serwer nie wysyła tekstu z audio, pola wiadomości: {list(data)}')
            now = time.monotonic()
            if self.last_audio_at and now - self.last_audio_at > 5:
                log(f'serwer wysłał następną paczkę po {now - self.last_audio_at:.0f} s (w pliku nic nie brakuje)')
            self.last_audio_at = now
        if not audio or data.get('isFinal'):
            log(f'wiadomość: {json.dumps(data)[:500]}')


def read_keys(presses):
    while True:
        presses.put(msvcrt.getwch().lower())


def set_speed(context, speed):
    for page in context.pages:
        try:
            page.evaluate(f'window.__edpSpeed = {speed}')
        except Error:
            pass


def main():
    parser = argparse.ArgumentParser(description='Zapisuje audio z ElevenReadera do pliku.')
    parser.add_argument('output', type=Path, nargs='?',
                        help='plik wyjściowy; bez nazwy: pierwszy wolny nagranie_N.mp3')
    parser.add_argument('--speed', type=float, default=16.0, help='prędkość odtwarzania (1 = normalna)')
    parser.add_argument('--url', default='https://elevenreader.io/')
    parser.add_argument('--chrome', type=Path, help='ścieżka do chrome.exe, jeśli nie jest w standardowym miejscu')
    args = parser.parse_args()

    chrome = args.chrome or next((p for p in CHROME_PATHS if p.is_file()), None)
    if not chrome or not chrome.is_file():
        raise SystemExit('Nie znalazłem chrome.exe - podaj ścieżkę przez --chrome')

    if args.output is None:
        n = 1
        while Path(f'nagranie_{n}.mp3').exists():
            n += 1
        args.output = Path(f'nagranie_{n}.mp3')
    log(f'Zapisuję do {args.output}')

    if args.output.exists():
        log(f'Plik istnieje - dopisuję na końcu ({args.output.stat().st_size / 1048576:.2f} MB)')

    chrome_proc = subprocess.Popen([
        str(chrome), f'--remote-debugging-port={CDP_PORT}', f'--user-data-dir={PROFILE_DIR}',
        '--no-first-run', '--no-default-browser-check', 'about:blank',
    ])
    with (sync_playwright() as pw, args.output.open('ab') as out,
          args.output.with_suffix('.txt').open('a', encoding='utf-8') as transcript):
        rec = Recorder(out, transcript)
        for _ in range(30):
            try:
                browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
                break
            except Error:
                time.sleep(0.5)
        else:
            chrome_proc.terminate()
            raise SystemExit('Nie udało się połączyć z Chrome (czy port 9222 jest wolny?)')

        context = browser.contexts[0]
        context.add_init_script(SPEED_JS)
        context.on('page', lambda page: page.on('websocket', rec.on_websocket))
        for page in context.pages:
            page.on('websocket', rec.on_websocket)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.url)
        log('Tryb pasywny: nic nie nagrywam, prędkość normalna.')
        log('W TERMINALU: SPACJA = nagrywaj/pauza, C = wyczyść plik, Ctrl+C = koniec.')

        presses = queue.SimpleQueue()
        threading.Thread(target=read_keys, args=(presses,), daemon=True).start()
        last_reported = -1
        last_status = time.monotonic()
        try:
            while browser.is_connected() and context.pages:
                context.pages[0].wait_for_timeout(300)
                while not presses.empty():
                    key = presses.get()
                    if key == '\x03':  # Ctrl+C przechwycone przez getwch
                        raise KeyboardInterrupt
                    if key == 'c':
                        out.seek(0)
                        out.truncate()
                        rec.total = 0
                        rec.seen.clear()
                        transcript.seek(0)
                        transcript.truncate()
                        log('WYCZYSZCZONO plik - zaczynam od zera')
                        continue
                    if key != ' ':
                        continue
                    rec.recording = not rec.recording
                    rec.last_audio_at = None
                    set_speed(context, args.speed if rec.recording else 1)
                    log(f'NAGRYWAM ({args.speed}x)' if rec.recording else 'PAUZA')
                if time.monotonic() - last_status >= 10 and rec.total != last_reported:
                    log(f'zapisano {rec.total / 1048576:.2f} MB')
                    last_reported = rec.total
                    last_status = time.monotonic()
        except (KeyboardInterrupt, Error):
            pass
        finally:
            chrome_proc.terminate()
    log(f'Koniec. Zapisano {rec.total / 1048576:.2f} MB do {args.output}')


if __name__ == '__main__':
    main()
