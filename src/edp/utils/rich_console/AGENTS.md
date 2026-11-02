# rich_console

Przenośny (współdzielony z mm_avh): preskonfigurowana `console`, motyw `RICH_THEME`, managery pasków postępu, helpery formatujące.

## Mapa katalogów

- `console.py` — instancja `console` z auto-highlightem URL/ścieżek/liczb (spany) i normalizacją przecinka dziesiętnego
- `theme.py` — `RICH_THEME` (150+ styli), klasa `Colors`, introspekcja styli
- `utilities.py` — bezstanowe helpery: ikony statusów, formatowanie bajtów/czasu/procentów, kolor progresu
- `progress/` — managery pasków (`ProgressBarManager`, `MultiProgressManager`, `ProgressBarBuilder`)
- `examples/` — dema palety/progresu/motywu + runner
- `tests/` — testy konsoli, motywu, progresu, `FORCE_COLOR`

## Pułapki

- Import `console.py` MONKEYPATCHUJE `console.print` na poziomie modułu — sam import zmienia zachowanie `print` (normalizacja liczb + highlight spanami), nie tylko udostępnia obiekt. `console.py`
- `FORCE_COLOR` czytany raz przy budowie konsoli w czasie importu — ustawienie zmiennej PO imporcie nie zadziała; wymusza sztywne `width=400`, `force_terminal=True`. `console.py`
- `console.print(..., highlight=False)` nadal opakowuje czyste stringi w `Text`, by nawiasy nie były parsowane jako markup — to nie zwykłe „wyłącz highlight" Richa. `console.py`
- Highlight to spany na surowym stringu; treść NIE jest re-parsowana jako markup, więc `[` i `\` w ścieżkach przetrwają dosłownie. `console.py`
- Kolejność wzorców w `_HIGHLIGHT_STYLES` jest znacząca — wcześniejszy dopasowany zakres blokuje nakładające się (URL > ścieżka > bool > liczba). `console.py`
- `get_status_icon` domyślnie zwraca STRING z tagami Rich markup (`[success]✅[/success]`) — trzeba go wypisać przez konsolę parsującą markup, inaczej pokażą się dosłowne nawiasy. `utilities.py`
- Ikony `warning`/`info`/`running`/`stopped` mają celowo doklejoną spację w emoji (`"⚠️ "` itd.) — string ikony nie jest „goły". `utilities.py`
- `format_bytes(binary=False)` używa bazy 1000 z jednostkami dziesiętnymi `KB/MB`; baza 1024 przełącza na `KiB/MiB`. `utilities.py`

## Konwencje

- Styl motywu `black` = „czarny na białym" (`rgb(0,0,0) on white`), nie sam czarny tekst. `theme.py`
- `logging.level/time/message` zakodowane na sztywno jako `"red"`, nie z palety `Colors`. `theme.py`
- `Colors.NORMAL` = `"default"` (kolor domyślny terminala), nie konkretny kolor. `theme.py`
- `format_bytes/duration/percentage`, `get_progress_color` rzucają `ValueError` na wartościach ujemnych / spoza 0–100, nie zwracają wyniku granicznego. `utilities.py` i in.

## Uwaga

- Standalone examples use `rich_console`; when nested, import `<pkg>.rich_console` with the utilities package prefix defined by the host.
