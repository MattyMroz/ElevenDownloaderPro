# timer

Przenośny (współdzielony z mm_avh): `Timer`, `ExecutionTimer`, `@timed`, `format_duration`. Wyświetlanie przez wspólną `console` z `rich_console`.

## Pułapki

- `stop()` po cichu zwraca `0`, gdy timer nie działa — nie rzuca. `__init__.py`
- `duration_ns` jest „na żywo": gdy timer działa, liczy do `perf_counter_ns()` w momencie odczytu, więc kolejne odczyty rosną. `__init__.py`
- Fallback używa `if self._end_time_ns` (truthy), nie `is None` — teoretyczny `end == 0` przełączyłby na tryb live. `__init__.py`
- `format_duration` mimo nazwy DRUKUJE do konsoli; zwracany string jest efektem wtórnym. `__init__.py`
- `start()` czyści pola `_end_*` — ponowny `start()` bez `reset()` kasuje poprzedni pomiar. `__init__.py`

## Konwencje

- Stringi używają nazwanych stylów Rich (`white_bold`, `yellow_bold`, `red_bold`, `ruby_red_bold`), które muszą istnieć w motywie `rich_console`. `__init__.py`
- `@timed` używa `except Exception` z `# noqa: BLE001`. `__init__.py`
- Format czasu to niestandardowe `HH:MM:SS:ms:µs:ns` (precyzja ns, dwukropki), nie ISO. `__init__.py`
- Importuje wspólny `console` z `..rich_console`, nie tworzy własnego. `__init__.py`

## Komenda

- Demo: `python -m <pkg>.timer` (przez `__main__.py`).
