---
kind: outcome
status: pending-human
baseline: a55aecd
resulting-state: .inf
completed: 2026-11-03
---

# Outcome 01: pełny refaktor na silnik ElevenReader z AniShift

## Status

- status: czeka na próbę Generała (userscript na żywej stronie, `edp download`) i na zgodę na zamknięcie zgłoszeń.
- branch: `main` @ `388e835`, wypchnięty.
- human acceptance: brak; scenariusz niżej.

## Finalny rezultat

- Pakiet `edp` (Python 3.14, `uv`) z CLI `edp`: `login`, `doctor`, `voices`, `record`, `download`. Każda komenda
  wypisuje jeden JSON na stdout i kończy się stałym kodem wyjścia (0, 1, 2, 3, 4).
- Silnik ElevenReader skopiowany z AniShift `origin/main` do `src/edp/engine/`, przenośna biblioteka `utils` 1:1 do
  `src/edp/utils/` (identyczna z `anishift/utils`, sprawdzone `diff -r`).
- `reading.py`: podział tekstu na części i dokumenty, najwyżej 2 nagrania naraz, ponowne czytanie cichych części,
  ponowienia błędów przejściowych, sklejanie MP3 po ramkach. `subtitles.py`: słowa i SRT.
- Userscript `userscript/edp.user.js` z tym samym kontraktem: nagrywa od otwarcia strumienia, reguły rejestratora
  silnika, tryb „wklej tekst i nagraj”, te same trzy pliki wynikowe.
- Czasy części, słów, napisów i `duration_ms` są na osi dekodera: przy zapisie przechodzą przez `to_decoded` ze
  szwami końcowego MP3 (`splice_times`), jak w AniShift `application/tts_clips.py`. Na osi serwera napisy
  spóźniały się o 26,12 ms na każdy szew, czyli o sekundy w godzinnych nagraniach. Próba na żywo (`lektor_pl.txt`,
  5 szwów): `duration_ms` 246 047,3 ms, tyle samo co po dekodowaniu FFmpegiem; oś serwera dawała 246 178,0 ms.
- Usunięte: `src/downloader.py`, `src/auto.py`, `src/timestamps.py`, `src/clips.py`, `script.js`, `docs/report.md`,
  `docs/research/capabilities.md`. Dodane: notatki research, `LICENSE` (MIT), szablony issue i PR, CI.

## Zgłoszenia

- **#1 (pierwsze ok. 2 minuty ucięte).** Przyczyna: strona wysyła pierwsze porcje audio przy wczytaniu dokumentu, przed
  Play, a stary userscript i downloader startowały z wyłączonym nagrywaniem i je odrzucały. Naprawa: obie drogi
  nagrywają od otwarcia strumienia; regresję łapią testy w Pythonie i JS. `edp download` odmawia dokumentu, który strona
  wznawia od środka, a userscript ostrzega o tym w panelu.
- **#2 (Tampermonkey nie działa).** Userscript przepisany od zera, ale przyczyny nie potwierdzono na żywej stronie.

## Dowody automatyczne

```text
uv run ruff check .            All checks passed
uv run ruff format --check .   121 files already formatted
uv run mypy .                  no issues in 110 source files
uv run pytest -n 6             1049 passed
node --test userscript/        79 passed, 0 failed
prek run --all-files           passed
uvx --from <wheel> edp voices  exit 0 (instalacja z wheela w czystym środowisku)
```

## Próba na żywo (orkiestrator, konto Generała)

- `edp record test.txt --voice fronczewski` (3 akapity, 273 znaki): kod 0, 16,5 s audio, pierwsze słowo od 0 ms,
  5 zdań w `.srt`, `silent: []`; po nagraniu `session.json` bez zaległych dokumentów i z przywróconymi ustawieniami.
- `edp record "rozdzial 1.5.txt"` na finalnym kodzie: kod 0, pliki `rozdzial 1.5.{mp3,json,srt}`, katalog roboczy
  usunięty, konto czyste.
- Zalogowany profil skopiowany z `.chrome-profile/` do `~/.edp/chrome-profile/`; źródło zostało na miejscu.

## Review

- Niezależne review (Sonnet): ACCEPT WITH FIXES, bez błędów krytycznych. Poprawione: nazwy plików z kropką, odmowa
  `download` dokumentu wznawianego od środka, zapis wyników bez utraty nagrań i JSON przy każdym błędzie, atomowy zapis
  `.json` i `.srt`, wyniki ukończonych plików przy Ctrl+C, scope `ci`, wersja ruff w hookach.
- Świadomie bez zmian: userscript nie sprząta zaległości konta sam (przycisk w panelu, żeby nie ścigać się z drugą
  kartą); przed startem strumienia innego dokumentu zapisuje nieukończone nagranie, żeby go nie stracić.

## Odchylenia od planu

- Przerwy ponowień 60/120/240 s zamiast 60/120/300 s (`build_retry` liczy wykładniczo z limitem).
- Zły tekst, za długa linia, zły adres, `--out` bez `.mp3` i dokument wznawiany od środka dają kod 2.
- Kilka plików w `edp record` nagrywa się po kolei, każdy z własną przeglądarką.
- Userscript wgrywa tekst przez interfejs biblioteki (Import, Upload), bo pól formularza `reads/add/v2` nie ma w żadnym
  źródle.
- Kopia silnika ma poza listą planu: wspólne `_stream` dla uploadu i downloadu, publiczne `part_bounds`,
  `stream_timeline`, `PART_GLUE` i `StreamRecorder.start_position`; `hub.py` bez zmian.

## Do sprawdzenia przez Generała

```text
Userscript:
  Zainstaluj https://raw.githubusercontent.com/MattyMroz/ElevenDownloaderPro/main/userscript/edp.user.js
  (Tampermonkey, w Chrome włączone „Allow User Scripts”), otwórz dokument od początku i poczekaj do końca;
  potem wklej krótki tekst w panelu i nagraj.
  Oczekiwane: panel widoczny, licznik rośnie od otwarcia dokumentu, trzy pliki po końcu, początek słychać.
  Jeśli nie działa (#2): konsola (wpisy [EDP], błędy CSP/Trusted Types), DevTools → Network → WS
  (adres stream/v2, czy z workera), WebSocket.toString() w konsoli.
edp download:
  edp download https://elevenreader.io/reader/library/<read_id krótkiego dokumentu> --out probe.mp3
  Oczekiwane: kod 0 i trzy pliki; dla dokumentu wznawianego od środka kod 2 z prośbą o przewinięcie.
Odsłuch: pauzy między akapitami i szwy po sklejaniu (dłuższy tekst z kilkoma dokumentami).
```

## Znane ograniczenia

- `MAX_DOCUMENT_CHARS = 50 000` to założenie z AniShift, nie pomiar.
- `--tags` niesprawdzone na żywo: jeśli serwer wytnie znaczniki z czasów znaków, części się nie dopasują.
- Książki z katalogu (DRM) mogą iść innym strumieniem; niesprawdzone.
- Głos i tempo to ustawienia całego konta: `edp` i AniShift naraz na jednym koncie przeszkadzają sobie.
- Lokalny `.browser-profile/` (22 MB, ignorowany przez git) nie ma odwołań w kodzie; zostawiony do decyzji Generała.
