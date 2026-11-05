# ElevenDownloaderPro

Nagrywanie mowy ElevenReadera (Eleven v4) do MP3 z czasami części, słów i napisami SRT: biblioteka i CLI `edp` w
Pythonie (silnik przeniesiony z AniShift, steruje prawdziwym Chrome przez CDP) oraz userscript Tampermonkey o tym samym
kontrakcie.

## Bramki jakości

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest -n 6
node --test userscript/
```

- Zawsze jawne `-n 6` (maszynę dzieli kilka sesji): hook `pytest` w pre-push ma je w `entry`, a CI uruchamia ten sam hook.
  `-n` nie trafia do `addopts`.
- `mypy` w trybie `strict` jest też hookiem `pre-push`; testy sieciowe (`-m network`) są domyślnie pomijane.

## Twarde reguły

- `src/edp/utils/` to przenośna biblioteka kopiowana 1:1 z AniShift (`anishift/utils`, manifest `_portable.py`).
  Nie zmieniaj jej tutaj; poprawka idzie do źródła i wraca kopią całego katalogu.
- `src/edp/engine/` to kopia silnika AniShift; dozwolone różnice opisuje `docs/plans/01-full-refactor.md`
  („Zmiany w kopii silnika”). Szczegóły silnika: `src/edp/engine/AGENTS.md`.
- Userscript i Python stosują te same reguły rejestratora i napisów. Zmiana reguły zmienia oba miejsca w jednym diffie,
  a oczekiwane wyniki w `tests/fixtures/` pochodzą z Pythona (`tests/test_subtitles.py` i `userscript/edp.user.test.js`
  czytają te same pliki).
- Kod domenowy loguje przez `edp.utils.logger.get_logger`; sink na stderr ustawia tylko `cli.py`.

## Mapa kodu

- `src/edp/cli.py`: komenda `edp` (`login`, `doctor`, `voices`, `record`, `download`); jeden JSON na stdout, logi na
  stderr, kody wyjścia 0 sukces, 1 odmowa, 2 użycie, 3 niekompletne, 4 anulowano (opis w `edp --help`).
- `src/edp/__init__.py`: publiczne API (`record`, `download`, `sign_in`, `read_session`, `VOICES`, `default_home`,
  błędy).
- `src/edp/reading.py`: jeden plik tekstowy → jeden dokument (części to niepuste linie); kilka plików nagrywa jeden
  silnik naraz, najwyżej `MAX_PARALLEL_DOCUMENTS` (2) dokumenty, bo konto ma 2 strumienie; ponowne czytanie cichych
  części, ponowienia błędów przejściowych, sklejanie MP3 po ramkach. Tekstu nie dzielimy: szew dokumentów zostawia
  w środku nagrania ok. 2 s ciszy z końca dokumentu.
- `src/edp/subtitles.py`: czasy znaków → `words` i zdania `.srt`; przy znanych częściach tylko znaki wypowiedzianych
  części (zakresy z `engine.service.part_bounds`).
- `src/edp/engine/`: jedna próba nagrania w karcie Chrome; ma własny `AGENTS.md`.
- `src/edp/errors.py`: `EdpError` → `TransientError` / `FatalError` → błędy `Tts*`.
- `userscript/edp.user.js`: userscript bez builda; czyste funkcje eksportuje dla `node --test` przez `module.exports`.
- `docs/research/`: protokół ElevenReadera, znaczniki v4, ciche porcje. `docs/plans/`: plan refaktoru.
- `workspace/`: lokalne katalogi robocze Generała; git śledzi tylko `.gitkeep`.

## Pułapki

- Katalog domowy `edp` (`--home`, `EDP_HOME`, domyślnie `~/.edp`) trzyma `chrome-profile/`, `session.json` i
  `chrome.lock`; `restrict_directory` zawęża jego uprawnienia przy starcie. Drugi proces na tym samym profilu dostaje
  `ChromeBusyError`.
- Głos i tempo to ustawienia całego konta ElevenReader (`user_config`): `edp` i AniShift na tym samym koncie naraz
  nadpisują sobie głos i limit 2 strumieni na urządzenie.
- Ten sam tekst z tym samym głosem serwer oddaje z cache jako identyczne MP3; nowe ujęcie wymaga zmienionego tekstu.
- Silnik, `PartTiming` i sklejanie liczą czas na osi serwera, a dekoder pomija jedną ramkę na każdym szwie strumienia
  (`mp3_frames.splice_times`). Czasy i `duration_ms` w `.json` oraz `.srt` przechodzą przez `to_decoded` dopiero przy
  zapisie wyników (`reading._decoded_time`, w userscripcie `decodedTime`). Do pliku MP3 trafiają tylko poprawne ramki
  (`reading._playable`, `playableFrames`): uszkodzona ramka na szwie dekoder pomija, ale FFmpeg (`-t`, `time=`,
  ffprobe) liczy ją jako czas, więc w pliku rozjeżdżałaby długość z `duration_ms`.
- Twarde zabicie `edp` zostawia Chrome na profilu; Ctrl+C idzie przez anulowanie i łagodne zamknięcie (kod 4).
- `edp download` odmawia (kod 2) dokumentu, który strona wznawia od środka (`position` > 0 w pierwszej wysłanej
  ramce); przewinięcia na początek przed Play nie znamy.
- Nagrania powstają w ukrytym katalogu roboczym obok plików wynikowych. Gdy zapis wyników się nie uda, katalog
  zostaje, a jego ścieżka jest w `error.details.recordings`.

## Dane runtime

- `workspace/` i `.chrome-profile/` zawierają nagrania i zalogowaną sesję Generała: nigdy ich nie usuwaj ani nie
  nadpisuj.

## Git

- Commit: nagłówek Conventional Commits po angielsku, `type(scope): opis`, ze scope'em z listy w `.pre-commit-config.yaml`; po pustej linii streszczenie „co i dlaczego”.
- Zero atrybucji AI w commitach i PR (trailery, stopki, emoji), także gdy host o nią prosi.
- Pliki dodawaj po nazwie, nigdy `git add .`; bez `--no-verify`. Worktree'y tylko w `.worktrees/<nazwa>`.
- Commit sprawdza pliki i nagłówek, push uruchamia bramki repo, CI resztę. Strażnicy w `.hooks/` to kopie z presetu `agents`; nie edytuj ich w repo.
