# utils

Portable utilities with no host application dependencies. The package facade exports only lightweight filesystem helpers. In commands below, `<pkg>` means the installed utilities package, including its host prefix when nested.

## Podpakiety (każdy ma własny AGENTS.md)

- `logger/` — logger loguru z sinkami JSON/Rich, scrubbingiem, readerami
- `rich_console/` — preskonfigurowana `console`, motyw, paski postępu
- `timer/` — `Timer`, `ExecutionTimer`, `@timed`, `format_duration`

## Luźne pliki

- `_retry.py` — presety tenacity (`NETWORK_RETRY` dekorator, `build_retry()` per-call)
- `device.py` — wybór CUDA>CPU bez importu torcha
- `mp3_frames.py` — ramki MPEG Layer III: nagłówki, ID3v2, czas serwera, cięcie przed czasem, miejsca sklejeń i przeliczenie na oś zdekodowaną; jedyny parser ramek w repo
- `safe_fs.py` — `safe_rmtree`/`safe_move` z retry na `PermissionError`
- `safe_path.py` — `safe_resolve` chroniący przed path traversal
- `secrets.py` — niemutujące redagowanie sekretów w dictach
- `timing.py` — `elapsed_ms_since` na zegarze monotonicznym
- `_portable.py` — manifest przenośności (moduły, zależności, smoke-testy)

## Pułapki

- `device.py` NIGDY nie importuje torcha sam — torch w `sys.modules` sprawia, że `onnxruntime.InferenceSession` używa cuDNN torcha i zwalnia ładowanie modeli ONNX o dynamicznym kształcie. `device.py`
- `DeviceInfo` ma pola `mps`/`has_mps`, ale żadna ścieżka nie zwraca `device="mps"` — `has_mps` zawsze `False`. `device.py`
- `build_retry` przekazuje `sleep=asyncio.sleep` przez referencję (late-binding), by `monkeypatch.setattr(asyncio,"sleep",...)` działał — przeniesienie do domyślnego argumentu ominęłoby patcha. `_retry.py`
- W `build_retry` `max_attempts` to CAŁKOWITA liczba wywołań (`stop_after_attempt`), nie liczba dodatkowych ponowień. `_retry.py`
- `_is_retryable_network_error` rozpoznaje `DownloadError` po nazwach w `__mro__` (lazy) i celowo NIE ponawia gdy w MRO jest też `OfflineError`. `_retry.py`
- `safe_rmtree`/`safe_move` pętlą `range(retries + 1)` — przy `retries=3` to 4 próby, backoff 0.5→1.0→2.0 s. `safe_fs.py`
- `safe_resolve` używa `is_relative_to` na już rozwiązanych ścieżkach (po `.resolve()` obu stron) — symlinki są śledzone przed sprawdzeniem. `safe_path.py`
- `mp3_frames`: ramka jest ważna tylko wtedy, gdy po niej stoi poprawny nagłówek albo kończą się dane. Zgubioną ramką (sklejeniem) jest wyłącznie ciąg bajtów między ważnymi ramkami, który zaczyna się poprawnym nagłówkiem: dekoder pomija go w całości, a czas serwera (`frames_duration_ms`, `cut_before_ms`) liczy go jako jedną ramkę. Obce bajty bez nagłówka nie są ani czasem, ani sklejeniem. Ostatnia ramka, po której do końca pliku stoją obce bajty, jest odtwarzana i liczy się jak zwykła ramka. `splice_times` zwraca czasy na osi zdekodowanej; `to_decoded` wymaga długości ramki strumienia (`FrameHeader.duration_ms`). `mp3_frames.py`
- Trzy różne `timing.py`: `utils/timing.py` (`elapsed_ms_since`), `utils/logger/timing.py` i `utils/timer/timing.py` — nie mylić przy imporcie.

## Konwencje

- Do not add the utilities directory itself to `sys.path`: `secrets.py` would shadow the standard-library module.
- `device.py` (sondowanie torch/ort) i `rich_console/progress/manager.py` używają `except Exception` mimo reguły „nigdy except Exception".
- `NETWORK_RETRY` ma budżet CZASOWY 60 s (`stop_after_delay`), `build_retry` limit LICZBY prób — dwa modele stopu. `_retry.py`
- Import retry helpers from `<pkg>._retry`, not the package facade. `TransientError` and `DownloadError` are recognized through MRO names without importing host exceptions.
