---
kind: plan
status: accepted
baseline: ElevenDownloaderPro a55aecd; AniShift origin/main 54c43cb
created: 2026-11-02
---

# Plan 01: pełny refaktor na silnik ElevenReader z AniShift

## Cel

Zamienić zbiór luźnych skryptów w bibliotekę Pythona `edp` z CLI, której rdzeniem jest przeniesiony silnik
ElevenReader z AniShift, i przepisać userscript tak, żeby robił w przeglądarce to samo i dawał te same pliki.

## Rezultat użytkownika

- `edp record rozdzial.txt --voice fronczewski` zapisuje obok pliku `rozdzial.mp3`, `rozdzial.json` i `rozdzial.srt`.
  Nagranie zaczyna się od pierwszego słowa. Akapit, którego serwer nie wypowiedział, zostaje przeczytany ponownie.
- `edp download <URL dokumentu>` nagrywa istniejący dokument z konta od początku i zapisuje te same trzy pliki.
- `edp login`, `edp doctor`, `edp voices` obsługują logowanie, diagnozę i listę głosów.
- Każda komenda wypisuje jeden obiekt JSON na stdout i kończy się stałym kodem wyjścia, więc agent AI obsłuży ją bez
  zgadywania. Przykład użycia stoi na górze `edp --help`.
- Userscript `edp.user.js` w Tampermonkey nagrywa otwarty dokument od początku albo wklejony tekst i zapisuje te same
  trzy pliki.

## Warunki końcowe

- [ ] W `src/` nie ma `downloader.py`, `auto.py`, `timestamps.py`, `clips.py`; w katalogu głównym nie ma `script.js`.
- [ ] `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run pytest -n 6` i
  `node --test userscript/` przechodzą lokalnie i w CI.
- [ ] Test regresji #1 (porcje przed Play trafiają do nagrania) przechodzi w Pythonie i w JS.
- [ ] Próba na żywo (faza 6) zaakceptowana przez Generała.
- [ ] Zgłoszenia #1 i #2 mają komentarz z wyjaśnieniem i są zamknięte (po zgodzie Generała).

## Nie-cel

- README: powstaje osobnym standardem. W tym planie zmieniamy w nim tylko zdania, które po refaktorze kłamią.
- Cięcie nagrania na klipy (robota AniShift), import formatów innych niż `.txt` (`.epub`, `.pdf`, `.docx`).
- Publikacja na PyPI.
- Zmiany w repozytorium AniShift.

## Decyzje Generała (2026-11-02)

01. Silnik przenosimy możliwie wiernie: te same pliki, zmienione tylko importy, teksty dla użytkownika i to, co służy
    wyłącznie AniShift.
02. Długi tekst: dzielimy na dokumenty do `MAX_DOCUMENT_CHARS` po granicy akapitu, nagrywamy (najwyżej 2 naraz) i
    sklejamy w jedno MP3 po ramkach, z czasami przeliczonymi na całość.
03. Znaczniki v4: domyślnie neutralizacja jak w silniku (`[` → `(`), flaga `--tags` przepuszcza je do serwera.
04. Dochodzą `LICENSE` (MIT © 2026 Mateusz Mróz), szablony issue i PR oraz CI na GitHub Actions.
05. Userscript ma działać jak biblioteka.
06. Zero legacy: stare pliki, nazwy i ścieżki znikają w tym samym diffie, bez aliasów i warstw zgodności.
07. `auto.py` i `clips.py` usuwamy bez następców.
08. `downloader.py` usuwamy; jego jedyna unikalna funkcja wraca jako `edp download <URL>` na kawałkach silnika.
09. `timestamps.py` usuwamy; napisy SRT i czasy słów wracają jako `subtitles.py` nad czasami znaków silnika.
10. Nazwa: ElevenDownloaderPro (pakiet `edp`, komenda `edp`).
11. Przenośną bibliotekę `anishift/utils` kopiujemy w całości 1:1 jako `src/edp/utils/`, z jej testami i zależnościami
    z `_portable.py` (`loguru`, `rich`, `pydantic`, `tenacity`).
12. Format wyniku (JSON na stdout, kody wyjścia) jest opisany w `edp --help` i w `AGENTS.md`.

## Authority i baseline

- Wymagania: decyzje wyżej. Konwencje: `AGENTS.md` repo, `.pre-commit-config.yaml`, globalne zasady Generała (zero
  legacy, testy z jawnym `-n`, najwyżej jedna ciężka rzecz naraz na sesję).
- Kod źródłowy silnika: **AniShift `origin/main` (54c43cb)**, czytany przez `git -C ../AniShift show origin/main:<ścieżka>`
  albo `git archive`. Lokalny `main` AniShift jest 13 commitów w tyle i nie ma wykrywania cichych porcji; z working
  tree AniShift nie kopiujemy nic.
- Baseline ElevenDownloaderPro: `a55aecd`, bramki zielone (`ruff`, `ruff format`, `mypy` na 4 plikach). Testów nie ma.

## Stan aktualny

### Obecne zachowanie i przyczyny zgłoszeń

- **#1 „first ~2 minutes cut off”.** Strona otwiera strumień i wysyła pierwsze porcje audio już przy wczytaniu
  dokumentu, przed Play (`src/auto.py:146-151,182-185`). Userscript startuje z `isRecording=false` i odrzuca ramki
  (`script.js:18-19,48`), downloader tak samo (`src/downloader.py:168,202`). Porcja ma do ok. 870 znaków (ok. 1 min),
  więc 1–2 porcje to 1–2 minuty. Silnik AniShift tego nie ma: `watch_stream` podpina rejestrator przed
  `open_document` (`service.py:240-242` na origin/main), rejestrator nie ma bramki, a `_result` odrzuca nagranie
  z `chars < char_count`.
- **#2 „Not working with Tampermonkey”.** Nierozstrzygnięte bez żywej strony. Hipotezy, od najmocniejszej: hak na
  `window.WebSocket` nie widzi strumienia (natywna referencja albo worker); w Chrome MV3 wyłączone „Allow User
  Scripts”; `innerHTML` blokowany przez Trusted Types; zmiana formatu ramek połknięta przez `catch (e) {}`
  (`script.js:64`). Rozstrzyga faza 6.
- Pozostałe wady `script.js`: brak filtra `stream/v2`, brak usuwania powtórzeń po ponownym połączeniu, brak kontroli
  modelu v4, autozapis po 60 s ciszy tnie plik, nadpisuje `document.onmousemove`/`onmouseup` strony.

### Do ponownego użycia

- Silnik: `anishift/services/tts/engines/elevenreader/` (`config`, `constants`, `types`, `service`, `api_backend`,
  `browser`, `hub`, `recorder`, `AGENTS.md`).
- `anishift/utils/` w całości (logger, `mp3_frames`, `_retry`, timer, rich_console, ...).
- `anishift/platform/process_lock.py`, `anishift/platform/private_dir.py` (z `is_windows` z `binaries.py:62-64`),
  `find_installed` z `anishift/platform/installed.py:16-26`.
- Błędy: `anishift/errors.py` (`ErrorCode` :26-95, `ErrorContext` :122-131, `AniShiftError` :134-150,
  `TransientError` :152, `FatalError` :188) i `anishift/services/tts/errors.py` :29-157.
- `TtsCancellation`: `anishift/services/tts/cancellation.py:12-74`.
- `atomic_json_snapshot`: `anishift/services/tts/artifacts.py:218-262` ze stałymi :25, :28.
- Typy dokumentu: `anishift/services/tts/types.py:297-355` (`DocumentPart`, `DocumentSynthesisRequest`,
  `PartTiming`, `EngineDocumentResult`).
- Ponowne czytanie: `anishift/services/tts/service.py` — `_read_lines` :1084, `_read_document` :1110,
  `_group_documents` :1389, `_unspoken_line_error` :1662.
- Kody wyjścia: `anishift/cli/exit_codes.py`.
- Reguły słów i zdań: `src/timestamps.py` (`split_words`, `split_sentences`, `write_srt`, `write_json`) w ElevenDownloaderPro `a55aecd`.
- Wzorce repo: `../AniShift/pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` bez `-n auto`),
  `../AniShift/.github/` (szablony issue, PR, `workflows/ci.yml`).

## Zakres

### In scope

- Pakiet `src/edp` z silnikiem, `utils`, CLI, ponownym czytaniem, sklejaniem i napisami; testy; `pyproject`.
- Userscript `userscript/edp.user.js` z testami `node --test`.
- Notatki research w `docs/research/`, `AGENTS.md`, scope'y hooków, `LICENSE`, `.github/`.
- Jednorazowe przeniesienie zalogowanego profilu `.chrome-profile/` do `~/.edp/chrome-profile/`.

### Forbidden

- Zmiany w `../AniShift` (tylko odczyt, także `config/elevenreader/` z cudzą sesją).
- Usuwanie czegokolwiek z `workspace/` (2,1 GB nagrań Generała) i z `.chrome-profile/` przed potwierdzonym
  przeniesieniem.
- Warstwy zgodności, aliasy starych nazw, `legacy`/`old`/`compat`.
- `git add .`, `--no-verify`, `-n auto`, push bez zielonych bramek.
- Zwykły Whisper w jakiejkolwiek postaci.
- Połączenia z ElevenReaderem poza fazą 6.

### Deferred

- Pomiar realnego limitu znaków dokumentu (zostaje `MAX_DOCUMENT_CHARS = 50 000`).
- Książki z katalogu Explore z DRM, jeśli faza 6 pokaże, że idą inną drogą.

### Dozwolone decyzje lokalne

- Nazwy prywatnych helperów, podział testów na pliki, kolejność argumentów prywatnych funkcji.
- Dokładne brzmienie komunikatów dla użytkownika (po angielsku, bez nazw AniShift, panelu i ElevenBytes).
- Wybór funkcji z `edp.utils.logger` do konfiguracji sinku na stderr.

### Zatrzymaj się i wróć po decyzję, gdy

- kopia silnika wymaga zmiany innej niż opisana w „Zmiany w kopii silnika”;
- `reading.py` nie da się zbudować na publicznym kontrakcie silnika bez zmiany `hub.py`;
- `utils` wymaga zależności spoza `_portable.py`;
- `download` wymaga endpointu, którego nie ma w `api_backend.py` ani w `docs/research/capabilities.md`.

## Target design

### Docelowe drzewo

```text
.github/
  ISSUE_TEMPLATE/{bug,feature,task,config}.yml   # CREATE (wzorzec AniShift)
  pull_request_template.md                       # CREATE
  workflows/ci.yml                               # CREATE
docs/
  plans/01-full-refactor.md                      # ten plan
  research/elevenreader-protocol.md              # CREATE z capabilities.md + pomiarów report.md
  research/elevenreader-tags.md                  # MODIFY (redakcja)
  research/silent-chunks.md                      # MODIFY (redakcja)
  research/capabilities.md                       # DELETE (wchłonięty)
  report.md                                      # DELETE (pomiary przeniesione)
  outcomes/01-full-refactor.md                   # CREATE po fazie 6
src/edp/
  __init__.py  __main__.py  cli.py               # CREATE
  errors.py  cancellation.py                     # CREATE (z AniShift)
  process_lock.py  private_dir.py                # CREATE (kopie z anishift/platform)
  reading.py  subtitles.py                       # CREATE
  engine/__init__.py config.py constants.py types.py service.py api_backend.py browser.py hub.py recorder.py AGENTS.md
  utils/...                                      # CREATE (kopia 1:1 anishift/utils)
  downloader.py auto.py timestamps.py clips.py   # DELETE (dziś w src/)
tests/
  conftest.py  fakes.py                          # z elevenreader_fakes.py
  engine/test_*.py  test_mp3_frames.py  test_process_lock.py  test_private_dir.py
  test_reading.py  test_subtitles.py  test_cli.py  test_import_boundary.py
  fixtures/                                      # wspólne dane Pythona i JS (ramki, oczekiwane .srt/.json)
userscript/
  edp.user.js  edp.user.test.js                  # CREATE
script.js                                        # DELETE
AGENTS.md  .pre-commit-config.yaml  pyproject.toml  uv.lock  .gitignore  LICENSE  README.md
```

### Odpowiedzialności

| element                  | odpowiada za                                                                                                                      | nie odpowiada za                                              |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `engine/`                | jedna próba: upload albo otwarcie dokumentu, ustawienie konta, nagranie, czasy części i porcje, sprzątanie konta                  | grupowanie, ponowne czytanie, sklejanie, pliki `.json`/`.srt` |
| `reading.py`             | tekst → części → dokumenty; ponowne czytanie cichych części; ponowienia błędów przejściowych; sklejenie MP3 i przeliczenie czasów | DOM, Playwright, format plików wynikowych                     |
| `subtitles.py`           | porcje (czasy znaków) → słowa i zdania; zapis `.json` i `.srt`                                                                    | nagrywanie                                                    |
| `cli.py`                 | argumenty, sink logów na stderr, JSON na stdout, kody wyjścia                                                                     | logika domeny                                                 |
| `utils/`                 | przenośna biblioteka, bez zmian                                                                                                   | —                                                             |
| `userscript/edp.user.js` | ten sam kontrakt w przeglądarce                                                                                                   | —                                                             |

Źródło prawdy dla stanu konta i zaległego sprzątania pozostaje `session.json` w katalogu domowym, zapisywany przez
`api_backend` (jak w AniShift).

### Katalog domowy

`--home` albo zmienna `EDP_HOME`, domyślnie `~/.edp`. Zawiera `chrome-profile/`, `session.json`, `chrome.lock`.
`restrict_directory` zabezpiecza go przy każdym starcie (jak w AniShift).

### Zmiany w kopii silnika (jedyne dozwolone)

- Importy `anishift.*` → `edp.*` (`edp.errors`, `edp.cancellation`, `edp.process_lock`, `edp.private_dir`,
  `edp.utils.logger`, `edp.utils.mp3_frames`).
- `config.py`: bez `TtsConfig` i `from_tts_config`; `ElevenReaderConfig(voice, profile_root)`; `find_installed`
  wklejony do `find_chrome`; `profile_dir(home) = home / "chrome-profile"`, `session_file(home) = home / "session.json"`.
- `service.py`: usuwamy `capabilities`, `synthesis_profile`, `availability`, `is_available`, `list_voices`,
  `synthesize`, `_chrome_availability`, `_build_availability`, `_voices` i sprawdzanie `options`/`provider_model_id`.
  Zostają `synthesize_document`, `validate_part`, `document_chars`, `close`, `_read`, `_record`, `_finished`,
  `_result`, `document_text`, `part_spans`, `_reported_here`.
- Nowa metoda `download_document(read_id, recording, *, voice_id: str | None, deadline_s, cancel)`: to samo co `_read`
  bez uploadu; `prepare_account` ustawia tempo 1x i głos tylko gdy podany; koniec nagrania wyłącznie po stanie
  odtwarzacza (`_finished`, gałąź `player_state`); brak `part_spans`. Dokument nie trafia do sprzątania (nie jest nasz).
- `types.py`: dochodzą `DocumentPart`, `DocumentSynthesisRequest` (bez `provider_model_id` i `options`, z polem
  `tags: bool = False`), `PartTiming`, `DocumentResult` (z `EngineDocumentResult` bez `format`, `engine_id`,
  `provider_model_id`, z polem `chunks: tuple[AlignmentChunk, ...]`).
- `_neutralize`/`document_text`/`part_spans`: gdy `request.tags`, nawiasy kwadratowe przechodzą bez zmian. `<break`
  w części jest odrzucany zawsze (psuje granice części).
- `api_backend.py`: `atomic_json_snapshot` wklejony jako funkcja prywatna; podpowiedzi „Ustawienia → Lektor” i
  ElevenBytes zastąpione `edp login`.
- `constants.py`, `browser.py`, `hub.py`, `recorder.py`: tylko importy i teksty (`anishift` → `edp` w nazwach wątku,
  pliku dokumentu, funkcji JS).
- Bez `MAX_DOCUMENT_CHARS` i bez odmowy dokumentu dłuższego niż 50 000 znaków w `_validate`: jeden plik tekstowy to
  jeden dokument. Limit nie miał pomiaru, a stary downloader nagrał jednym dokumentem 143 870 znaków (MS3_010).
- `browser.py`: `ChromeBusyError` jest trwały (`TtsError`, `FatalError`), a nie przejściowy jak w AniShift. Zajęty
  profil w `edp` to drugi proces CLI albo zawieszony Chrome; ponowienia co minutę tylko ukrywały, że nic nie nagrywa.
- `AGENTS.md` silnika: odwołania do `TtsService`, schedulera, doctora i panelu zastąpione `reading.py` i `cli.py`.

### Publiczne API (`edp/__init__.py`)

```text
record(text: Path, *, voice: str, out_dir: Path | None = None, tags: bool = False, home: Path = default_home()) -> RecordResult
download(url: str, *, out: Path, voice: str | None = None, home: Path = default_home()) -> RecordResult
sign_in(home) -> SignInOutcome      read_session(home) -> SessionRecord | None
VOICES, default_home(), EdpError, TransientError, FatalError
RecordResult: mp3, json, srt: Path; duration_ms: float; parts: tuple[PartTiming, ...]; silent: tuple[int, ...]
```

`record` i `download` są synchroniczne (`asyncio.run` w środku), bo konsumentem jest CLI i skrypty.

### Plik `<nazwa>.json` (wspólny dla Pythona i userscriptu)

```json
{
  "audio": "rozdzial.mp3",
  "voice": "fronczewski",
  "duration_ms": 123456.0,
  "parts": [{"index": 0, "text": "…", "start_ms": 0.0, "end_ms": 4200.0, "spoken": true}],
  "words": [{"text": "Dzień", "start_ms": 0.0, "end_ms": 310.0}],
  "silent": []
}
```

`download` zapisuje `"parts": []`. Czasy są w osi serwera (`mp3_frames.frames_duration_ms`), liczone od początku
wynikowego MP3.

### CLI `edp`

| komenda                                                         | działanie                                                        | stdout                                                |
| --------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------- |
| `edp login`                                                     | okno Chrome do zalogowania (do 600 s) i zaległe sprzątanie konta | `{"outcome": "signed_in"}`                            |
| `edp doctor`                                                    | Chrome, sesja, zaległe sprzątanie; bez przeglądarki              | `{"chrome": …, "signed_in": …, "cleanup_pending": …}` |
| `edp voices`                                                    | głosy z `VOICES`                                                 | `[{"alias", "label", "voice_id"}]`                    |
| `edp record PLIK.txt... --voice ALIAS [--out KATALOG] [--tags]` | każdy plik → `.mp3`, `.json`, `.srt` obok pliku albo w `--out`   | `{"results": [...]}`                                  |
| `edp download URL [--out PLIK.mp3] [--voice ALIAS]`             | istniejący dokument → trzy pliki                                 | `{"results": [...]}`                                  |

Wspólne: `--home`. Kody wyjścia: 0 sukces; 1 odmowa (konfiguracja, logowanie, głos, kredyty, brak Chrome);
2 błąd użycia (argparse); 3 niekompletne (cicha część po wszystkich próbach albo błąd przejściowy po ponowieniach);
4 anulowano (Ctrl+C). Błąd oczekiwany: komunikat na stderr, bez tracebacku. `read_id` wyciąga się z URL
`https://elevenreader.io/reader/<…>/<read_id>` (format potwierdzić w `src/downloader.py` i `capabilities.md`).

### Algorytm `reading.py`

1. **Części.** Tekst UTF-8 → części: każda niepusta linia po `strip()` to jedna część (`DocumentPart(id=str(i), text)`).
   Każda część przechodzi `validate_part`; błąd wskazuje numer linii.
2. **Dokumenty.** Części grupuje się po kolei w dokumenty, póki `document_chars` ≤ `MAX_DOCUMENT_CHARS`. Pojedyncza
   część ponad limit to błąd użycia.
3. **Nagranie.** Dokumenty nagrywa jeden `ElevenReaderTtsEngine` na `home`, najwyżej `MAX_PARALLEL_DOCUMENTS` (2)
   naraz (`asyncio.Semaphore`). Nagrania trafiają do katalogu tymczasowego.
4. **Ponowienia.** `TransientError` całego dokumentu ponawia `edp.utils._retry.build_retry`: 3 ponowienia, przerwy
   60/120/300 s. `FatalError` przerywa wszystko.
5. **Ciche części** (port `_read_lines`): części z `spoken == False` po pierwszym przebiegu czyta się razem jako jeden
   mniejszy dokument, gdy jest ich więcej niż jedna i mniej niż w dokumencie źródłowym; części wciąż ciche czyta się
   osobno, gdy ostatni dokument miał więcej niż jedną część. Najwyżej dwa ponowne odczyty na część; dokument identyczny
   z już przeczytanym nie jest powtarzany. Część cicha po wszystkich próbach trafia do `silent` i daje kod 3.
6. **Sklejenie.** Każda wypowiedziana część dostaje odcinek z nagrania, w którym została wypowiedziana: od jej
   `start_ms` (dla pierwszej części nagrania od 0) do `start_ms` następnej wypowiedzianej części tego samego nagrania,
   a dla ostatniej do końca nagrania. Odcinki w kolejności części łączy się po ramkach (`mp3_frames.cut_before_ms` i
   pokrewne), bez dekodowania. Czasy części i słów przesuwa się o początek odcinka w wyniku.
7. **Zapis.** `subtitles.py` zapisuje `.json` i `.srt`; MP3 zapisuje się atomowo (plik tymczasowy + `replace`).

### Userscript

- Nagłówek: `@name ElevenDownloaderPro`, `@version 2.0.0`, `@match https://elevenreader.io/*` (`elevenlabs.io` usuwamy, chyba że faza 6
  pokaże tam strumień), `@run-at document-start`, `@grant none`, `@updateURL` i `@downloadURL` na
  `https://raw.githubusercontent.com/MattyMroz/ElevenDownloaderPro/main/userscript/edp.user.js`.
- Hak na `WebSocket` ustawiony przy `document-start`, przed skryptami strony. Nagrywa **od otwarcia strumienia**
  `…/reads/stream/v2/…`, bez przycisku „RECORD”.
- Reguły jak w `engine/recorder.py`: dekodowanie `audio` z base64, usuwanie powtórzeń i przycinanie po ponownym
  połączeniu (port `trim_chunk`/`rfind_all`), cicha porcja (≥ 20 liter i < 10 ms na literę) jako ostrzeżenie w panelu,
  `listening_speed` ≠ 1 na pierwszej ramce jako błąd „model v2: ustaw tempo konta 1x” z przyciskiem, który to robi,
  koniec po `isFinal`.
- Tempo odtwarzania strony jak `constants.SPEED_JS` (64x, ta sama technika).
- Token strony łapany z nagłówka `authorization` żądań strony (jak `ReaderPage._remember_token`). Tryb „wklej tekst i
  nagraj”: upload jak `ReaderPage.upload` (ten sam endpoint i pola), `user_config` jak `prepare_account` (głos z listy
  `VOICES`, tempo 1x), po nagraniu `DELETE` dokumentu i przywrócenie ustawień jak `clean_account`.
- Zapis `.mp3`, `.json` (schemat wyżej), `.srt` tymi samymi regułami co `subtitles.py`.
- Panel: tworzony przez `createElement`/`textContent` (bez `innerHTML`), przeciąganie przez `addEventListener`,
  każdy błąd widoczny w panelu i w `console.error` z prefiksem `[EDP]`.
- Czyste funkcje eksportowane dla Node na końcu pliku: `if (typeof module === "object") module.exports = {...}`;
  inicjalizacja DOM tylko, gdy istnieje `window`.

## Plan wykonania

Fazy 1–2 i 4 robią wykonawcy w worktree `.worktrees/<nazwa>` na gałęziach `refactor/<nazwa>`, commitując według
`AGENTS.md` (Conventional Commits, `mm-validate`). Integruje i pushuje orkiestrator po review.

### Faza 0 — preflight (orkiestrator)

- Commit tego planu na `main`. Worktree'y: `.worktrees/engine` (gałąź `refactor/engine`), `.worktrees/userscript`
  (`refactor/userscript`).
- **Gate:** `git worktree list` pokazuje oba, `main` czysty.

### Faza 1 — pakiet, silnik, utils (writer A)

1. `pyproject.toml`: `[build-system]` `uv_build`, `[project.scripts] edp = "edp.cli:main"`, `uv remove miniaudio`,
   `uv add loguru rich pydantic tenacity` (wersje z `_portable.py` jako dolne granice, `playwright` zostaje),
   `uv add --dev pytest pytest-xdist` i wtyczki testowe, których używają przenoszone testy (sprawdzić w
   `../AniShift/pyproject.toml`). `[tool.ruff]` i `[tool.mypy]` jak w AniShift (`target-version = "py314"`).
   `[tool.pytest.ini_options]` jak w AniShift, ale bez `-n` w `addopts`; `testpaths = ["tests", "src/edp/utils"]`;
   markery `unit`, `integration`, `network` z `--strict-markers`.
2. Kopia `anishift/utils` → `src/edp/utils` przez `git archive`, potem zamiana prefiksu pakietu w importach i
   docstringach. Nic więcej.
3. `errors.py`, `cancellation.py`, `process_lock.py`, `private_dir.py` według „Do ponownego użycia”. Hierarchia:
   `EdpError` (z `AniShiftError`) → `TransientError` / `FatalError` → błędy `Tts*` (nazwy klas bez zmian).
4. Kopia silnika do `src/edp/engine/` ze zmianami wyłącznie z „Zmiany w kopii silnika” (bez `download_document`, ten
   wchodzi w fazie 2).
5. Testy: `elevenreader_fakes.py` → `tests/fakes.py`; testy recordera, api_backend, browser, config (bez
   `from_tts_config`), service (bez testów protokołu AniShift i `availability`), `test_mp3_frames.py`,
   `test_process_lock.py`, `test_private_dir.py`, test granicy importu Playwright. Nie przenosimy
   `test_tts_elevenreader_service_data.py` ani `test_tts_elevenreader_network.py`.
6. Commity: `build(deps)`, `feat(utils)`, `feat(engine)`, `test(engine)` (scope'y dopisane w `.pre-commit-config.yaml`
   w tym samym diffie, zob. faza 4).

**Kontrola:** `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run pytest -n 6`; liczba
testów silnika po przeniesieniu podana w wyniku i porównana z liczbą przed (różnica wyjaśniona listą usuniętych).

**Gate:** wszystko zielone; `grep -rn "anishift" src tests` zwraca tylko nazwy w historii dokumentacji.

### Faza 2 — reading, subtitles, CLI, usunięcie starych skryptów (writer A, wznowiony)

1. `download_document` w silniku, `reading.py`, `subtitles.py`, `cli.py`, `__init__.py`, `__main__.py` według
   designu.
2. `git rm src/downloader.py src/auto.py src/timestamps.py src/clips.py`.
3. Testy kontraktu (na fake'ach silnika z `tests/fakes.py`, bez przeglądarki):
   - `test_reading`: podział na części i dokumenty z limitem; ponowne czytanie (port 4 testów z
     `origin/main:tests/services/tts/test_tts_document_service.py:432-493`); sklejenie dwóch nagrań-fixture po ramkach
     z poprawnymi czasami; część cicha po wszystkich próbach → `silent` i kod 3; ponowienie błędu przejściowego.
   - `test_subtitles`: fixture porcji → oczekiwane `.srt` i `.json` w `tests/fixtures/` (te same pliki czyta test JS).
   - `test_cli`: `--help` zawiera przykład; `voices` i `doctor` dają poprawny JSON i kod 0; brak Chrome → kod 1;
     zły argument → kod 2; `record` na fake'u → trzy pliki i JSON na stdout.
   - Regresja #1: fake strumienia wysyła porcję przed Play → jest w MP3 i w `words`.
4. Jednorazowy `scripts/tmp/move_profile.py`: kopiuje `.chrome-profile/` do `~/.edp/chrome-profile/`, nie usuwa
   źródła. Uruchamia go orkiestrator w fazie 6, potem plik znika (nie trafia do commita).

**Kontrola:** jak w fazie 1 + `uv run edp --help`, `uv run edp voices`, `uv run edp doctor` (bez sieci).

**Gate:** zielone bramki, nowe testy przechodzą i potrafią zawieść (sprawdzone przez chwilowe zepsucie asercji lokalnie,
bez commita).

### Faza 3 — userscript (writer B, równolegle z fazą 2)

1. `userscript/edp.user.js` według designu; `git rm script.js`.
2. `userscript/edp.user.test.js` (`node:test`): dedup i przycinanie po ponownym połączeniu, cicha porcja, wykrycie v2,
   słowa i SRT na fixture z `tests/fixtures/` (jeśli faza 2 jeszcze ich nie ma, writer B tworzy je w tym katalogu
   z danych `src/timestamps.py` przy `a55aecd`, a writer A ich używa), regresja #1 (ramka przed Play jest zapisana).
3. Commit `feat(userscript)`.

**Kontrola:** `node --test userscript/`; `node --check userscript/edp.user.js`.

**Gate:** testy zielone; w pliku brak `innerHTML`, `onmousemove =`, pustego `catch`.

### Faza 4 — dokumentacja i repo (writer C, po fazach 2 i 3)

1. Notatki research (po polsku, styl według skilla miodkuj, fakty tylko ze źródeł):
   - `elevenreader-protocol.md` z `capabilities.md` (bez sekcji o starym narzędziu i bez zdania o 3 kartach ≈ 17x,
     które przeczy pomiarowi z 2026-10-31: najwyżej 2 strumienie na urządzenie) i z pomiarów `report.md`
     (przepustowość 4,5–5,5x, powyżej 16x bez zysku, v4 tylko przy 1x, model ustalany przy starcie strumienia, cache
     tego samego tekstu, czasy znaków wyprzedzają mowę o ok. 0,3 s).
   - `elevenreader-tags.md` i `silent-chunks.md`: redakcja i dopisek, co z tego jest wdrożone w `edp`.
   - `git rm docs/report.md docs/research/capabilities.md`.
2. `AGENTS.md`: mapa kodu, bramki (`pytest -n 6`, `node --test`), format JSON i kody wyjścia, pułapki (limit 2
   strumieni, tempo 1x, katalog domowy, Chrome zamykany łagodnie).
3. `.pre-commit-config.yaml`: scope'y `repo,docs,deps,engine,utils,cli,userscript,ci`; komentarz
   `default_language_version` bez `downloader.py`; `ruff-pre-commit` wyrównany do wersji z `uv.lock`.
4. `LICENSE` (MIT, © 2026 Mateusz Mróz); `.github/` ze wzorca AniShift: szablony issue i PR, `ci.yml` z jobami lint,
   typecheck, test (`-m "not network" -n logical`, ubuntu i windows; lokalnie zostaje jawne `-n 6`), userscript (`node --test`).
5. README: tylko poprawki zdań, które po refaktorze są fałszywe (ścieżki, komendy).

**Kontrola:** `prek run --all-files`, `prek run --hook-stage manual --all-files`,
`python ../agents/scripts/standard.py check --project .`, `actionlint` jeśli dostępny.

### Faza 5 — niezależne review (świeży reviewer)

Reviewer dostaje plan i finalny diff, nie uzasadnienia autorów. Szuka: odchyleń od „Zmian w kopii silnika”,
legacy, błędów sklejania czasu, rozjazdu reguł Python ↔ JS, brakujących testów kontraktu. Orkiestrator poprawia i
ponawia bramki.

### Faza 6 — próba na żywo (Generał + orkiestrator)

Wgrywa dokumenty na konto Generała i tymczasowo zmienia głos; silnik sprząta i przywraca.

```text
Uruchom: uv run python scripts/tmp/move_profile.py; uv run edp doctor
Zrób:    uv run edp record <krótki tekst 3 akapity>.txt --voice fronczewski
         uv run edp download <URL dokumentu z konta>
         zainstaluj userscript z gałęzi, otwórz dokument, poczekaj na koniec; potem tryb „wklej tekst”
Oczekiwany rezultat: trzy pliki na każdą próbę, pierwsze słowo słychać od początku, .srt zgodne z mową,
         na koncie nie zostaje wgrany dokument, głos konta wraca do poprzedniego
Zwróć uwagę na: pauzę „…” między akapitami, początek nagrania, objaw #2 (panel? licznik? błąd w konsoli?)
Przekaż wynik jako: OK / opis problemu + plik
```

Diagnoza #2: DevTools → Network → WS (adres, wątek inicjujący, format ramek), konsola (`[EDP]`, CSP/Trusted Types),
`WebSocket.toString()`. Poprawka trafia do userscriptu przed zamknięciem fazy.

### Faza 7 — zamknięcie (orkiestrator, po zgodzie Generała)

`docs/outcomes/01-full-refactor.md`; merge do `main`, push z zielonym pre-push i CI; komentarz w #1 i #2 z przyczyną
i wersją poprawki, zamknięcie zgłoszeń.

## Dodatkowi wykonawcy

| jednostka           | write scope                                                                                             | wynik                                                   | integracja   |
| ------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------ |
| writer A (fazy 1–2) | `.worktrees/engine`: `src/`, `tests/`, `pyproject.toml`, `uv.lock`, scope'y w `.pre-commit-config.yaml` | commity na `refactor/engine`, liczby testów, odchylenia | orkiestrator |
| writer B (faza 3)   | `.worktrees/userscript`: `userscript/`, `script.js`, `tests/fixtures/` (tylko nowe pliki)               | commit na `refactor/userscript`                         | orkiestrator |
| writer C (faza 4)   | `docs/`, `AGENTS.md`, `.pre-commit-config.yaml`, `LICENSE`, `.github/`, `README.md`                     | commity                                                 | orkiestrator |
| reviewer (faza 5)   | tylko odczyt                                                                                            | findingi z dowodami                                     | orkiestrator |

Każdy brief zawiera regułę zero legacy, zakaz Whispera i limit zasobów (testy `-n 6`, jedna ciężka rzecz naraz).

## Strategia dowodu

| twierdzenie                                                | kontrola                                                |
| ---------------------------------------------------------- | ------------------------------------------------------- |
| silnik po przeniesieniu działa jak w AniShift              | przeniesione testy na fake'ach, liczby przed i po       |
| #1 naprawione                                              | test regresji w Pythonie i JS + faza 6                  |
| ponowne czytanie i sklejanie dają ciągłe MP3 i dobre czasy | `test_reading` na fixture MP3 + odsłuch w fazie 6       |
| SRT i słowa identyczne w Pythonie i JS                     | oba testy na tych samych plikach w `tests/fixtures/`    |
| CLI nadaje się dla agenta                                  | `test_cli` (JSON, kody wyjścia, przykład w `--help`)    |
| #2 naprawione                                              | faza 6 na żywej stronie                                 |
| repo zgodne ze standardem                                  | `standard.py check`, `prek run --all-files`, zielone CI |

## Ryzyka i reakcje

| ryzyko                                                                              | jak rozpoznać                           | reakcja                                                                    |
| ----------------------------------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------- |
| `MAX_DOCUMENT_CHARS = 50 000` to założenie, nie pomiar                              | błąd serwera przy dużym dokumencie      | zostaje; pomiar jako osobny rezultat                                       |
| pauza `…` między akapitami psuje rytm audiobooka                                    | odsłuch w fazie 6                       | decyzja Generała przed fazą 7                                              |
| `download` dla książek z katalogu idzie inną drogą (DRM)                            | brak ramek `audio` w fazie 6            | odnotować w outcome, osobny rezultat                                       |
| głos i tempo to ustawienie całego konta; `edp` i AniShift naraz sobie przeszkadzają | zmieniony głos w AniShift               | pułapka w `AGENTS.md`                                                      |
| twarde zabicie CLI zostawia Chrome na profilu                                       | `chrome.lock` zajęty, `ChromeBusyError` | komunikat z instrukcją; Ctrl+C idzie przez anulowanie i łagodne zamknięcie |
| `restrict_directory` zmienia ACL katalogu domowego                                  | błąd dostępu po przeniesieniu profilu   | `move_profile.py` kopiuje, nie przenosi; źródło zostaje do potwierdzenia   |
| status 402 jako brak kredytów jest niepotwierdzony (przechodzi z AniShift)          | —                                       | bez zmian, pułapka w `AGENTS.md`                                           |

## Definition of Done

- [ ] warunki końcowe spełnione;
- [ ] bramki zielone lokalnie i w CI, z liczbami w commitach (`Validation:`);
- [ ] review bez otwartych findingów;
- [ ] faza 6 zaakceptowana przez Generała;
- [ ] outcome zapisany, zgłoszenia zamknięte.
