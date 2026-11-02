# engine

Silnik dokumentowy przeniesiony z AniShift: jedna próba wgrywa dokument do ElevenReadera, nagrywa strumień w Chrome i
zwraca nagranie MP3 z czasami części (`PartTiming`) i porcjami strumienia (`AlignmentChunk`). Grupowanie tekstu w
dokumenty, ponowne czytanie cichych części, sklejanie i pliki `.json`/`.srt` robi `reading.py` i `subtitles.py`, nie
silnik. Zmiany względem AniShift ogranicza plan `docs/plans/01-full-refactor.md` („Zmiany w kopii silnika”).

## Moduły

- `config.py`, `constants.py`, `types.py`, `service.py` (silnik, `document_text`, `part_spans`, `stream_timeline`,
  `part_bounds`) i `api_backend.py` (karta Playwright: `ReaderPage`, konto, sesja, mapowanie błędów dostawcy).
- `part_bounds` jest jedynym miejscem, które dzieli strumieniowany tekst na części; `part_spans` i `subtitles.py`
  liczą z niego zakresy znaków, więc separator `…` i `<break>` nigdy nie stają się słowem.
- `synthesize_document` wgrywa dokument i go usuwa; `download_document` nagrywa istniejący dokument z biblioteki bez
  uploadu i bez sprzątania dokumentu, z głosem konta (`voice_id=None`) albo podanym. Koniec nagrania rozpoznaje
  wyłącznie stan odtwarzacza, bo bez uploadu nie ma `char_count`; wynik ma `parts=()`. Bramka głosu traktuje głos
  konta jako osobny klucz (`_ACCOUNT_VOICE`), więc pobieranie nie nagrywa razem z innym wybranym głosem.
- `StreamRecorder.start_position` to `position` z pierwszej ramki wysłanej przez stronę, zanim przyszedł tekst.
  Download z `start_position` > 0 kończy się `TtsInputError` (bez ponowień): strona wznawia dokument od środka.
- `browser.py` (proces Chrome i CDP; tu też `ChromeMissingError` i `ChromeBusyError`), `hub.py` (`ReaderHub`: jedna
  przeglądarka profilu w procesie, karta na nagranie, wspólne sprzątanie konta) oraz `recorder.py` (czyste ramki
  WebSocket → MP3 i czasy znaków, testowane bez przeglądarki).

## Gospodarz (`hub.py`)

- `ReaderHub.acquire(profile_root, …)` w konstruktorze silnika, `release()` w `close()`; rejestr procesu pod
  `threading.Lock`, licznik referencji = żywe silniki. Gospodarz ma własny wątek `edp-elevenreader` (daemon) i pętlę
  asyncio; na niej żyją `ChromeSession`, karty, `AccountCleanup` i każdy zapis `session.json`. Silniki z różnych pętli
  (`reading.py` nagrywa najwyżej `MAX_PARALLEL_DOCUMENTS` dokumentów naraz) zlecają całą próbę przez `record` i nie
  dotykają Playwright.
- Nowy gospodarz profilu, którego poprzedni jeszcze się zamyka, czeka w swoim wątku na koniec poprzedniego i dopiero
  wtedy wczytuje `load_cleanup`; ostatni `release` sprząta konto w nowej karcie, zapisuje, ostrzega
  (`CLEANUP_WARNING`), zamyka Chrome i kończy wątek.
- Próba: bramka głosu (poza terminem, pod anulowaniem; inny głos czeka na koniec aktywnych, kolejka po bilecie bez
  głodzenia) → termin `request.deadline_s` → blokada startu: Chrome (start albo restart podejrzanego, gdy nikt inny
  nie nagrywa), karta, `require_signed_in`, zaległe dokumenty, upload, `prepare_account`, Play; blokadę zwalnia
  `attempt.started()` po pierwszym adresie strumienia albo po `START_TIMEOUT_S` → nagrywanie równolegle → `_leave`.
- Anulowanie: `Cancellation` wywołującego i anulowanie zadania silnika przechodzą przez osobny `Cancellation` próby
  (`_until_done`); silnik wraca dopiero po końcu `_leave` tej próby. Postęp dokumentu wraca na pętlę silnika
  (`_reported_here`, `run_coroutine_threadsafe`).

## Granice

- Na poziomie modułu Playwright importuje tylko `browser.py`. `api_backend.py` ładuje go leniwie
  (`_playwright_error`, `_playwright_timeout`, import `browser` w `sign_in`), a `hub.py` ładuje `browser.py`
  w `headless_session`. Pilnują tego oba testy w `tests/test_import_boundary.py`.
- `find_chrome`, `profile_dir` i `session_file` leżą w `config.py`, żeby `edp doctor` nie ładował Playwright.
- `ChromeSession` startuje Chrome z `--user-data-dir=<katalog domowy>/chrome-profile` (Chrome 136+ ignoruje CDP dla
  domyślnego profilu) na wolnym porcie i dołącza `connect_over_cdp`. Proces jest zwykłym dzieckiem procesu `edp`.
- `ChromeSession.close` najpierw prosi Chrome o wyjście przez CDP (`Browser.close`) i czeka do 10 s; `terminate`
  i `kill` są tylko zapasem. Chrome zapisuje ciasteczka na dysk z opóźnieniem do ok. 30 s, więc twarde zabicie
  zaraz po zalogowaniu gubi sesję (`signed_in: true` w `session.json`, a profil wylogowany).
- Nagrywanie, sprzątanie i sprawdzanie sesji przez silnik działają tylko z `headless=True` (`headless_session`);
  okno widać wyłącznie w `sign_in` (`edp login`). Skrypty diagnostyczne też nie otwierają okna.
- `ProcessLock` na `chrome.lock` wyklucza drugą przeglądarkę na profilu (drugi proces, okno logowania): zajęty →
  `ChromeBusyError` (przejściowy); w `sign_in` → `SignInOutcome.BUSY`. W procesie Chrome profilu ma tylko gospodarz.
  `restrict_directory` przy każdym starcie.
- `ReaderPage` jest jedynym miejscem z selektorami i wywołaniami Playwright. Każdy błąd Playwright idzie przez
  `map_playwright_error` z `from None`, bo komunikat Playwright potrafi zawierać adres z `read_id`.

## Konto i sprzątanie

- Głos i tempo 1x ustawia `user_config` konta tokenem strony (`prepare_account`), przed otwarciem dokumentu:
  serwer wybiera model przy starcie strumienia. Wpis przywrócenia (we wspólnym `AccountCleanup` gospodarza) powstaje
  przed zapisem i nie jest nadpisywany, dopóki poprzedni nie wykona się, inaczej „poprzednim” głosem zostałby nasz.
- Każda próba ma własny `AccountCleanup` wgrań (`ReaderAttempt.uploads`); gospodarz ma wspólny (`restore` i dokumenty
  zakończonych prób). `session.json` zapisuje sumę obu (`_save`). `clean_account(…, restore=…)`: w `_leave` (pod
  `finish_shielded`, także po anulowaniu) próba usuwa tylko swoje dokumenty; resztki przechodzą do wspólnego, a
  próba, po której nie zostaje żadna otwarta karta, pod blokadą startu przywraca ustawienia (`restore=True`).
  Licznik kart `_tabs` spada na samym początku `_leave`, nie w `_exit`, więc dwie próby kończące się naraz nie
  pomijają przywrócenia nawzajem. Start próby usuwa zaległe dokumenty bez przywracania ustawień. Każdy krok ma własny
  limit i `_cleanup_step` łapie każdy wyjątek; karta zamyka się w `finally`, a slot bramki głosu zwalnia zawsze.
  Zaległe kroki biegną też przy ostatnim `release` (jeśli przeglądarka żyje) i w `sign_in` (`edp login`). Trwała
  porażka: `logger.warning(CLEANUP_WARNING, steps=…)` i `cleanup_pending` w `edp doctor`.
- `upload` dopisuje `DocumentTrace` każdego wgrania (`pressed_at` i `listed_by` jako czas zegarowy `time.time()`,
  skróty SHA-256 możliwych tytułów z `document_titles`) i zapisuje go przed „Upload”, a `read_id` z odpowiedzi
  wpisuje do śladu przed walidacją `char_count`/tokenu. Dokument ze znanym `read_id` znika przez `DELETE reads/{id}`,
  także po restarcie, bo `read_id` jest zapisany w `session.json`.
- Tylko upload bez odpowiedzi z `read_id` (anulowanie w trakcie uploadu, odpowiedź bez id) szuka się w pierwszej
  stronie `GET reads`: `from_user_import is True`, `original_file_type == "text/plain"`, `added_at_unix` w
  `[pressed_at − 300 s, listed_by + 300 s]` i skrót znormalizowanego `title` wśród skrótów śladu. Serwer bierze tytuł
  z pierwszego zdania treści, nie z nazwy pliku, więc ślad trzyma skróty każdego prefiksu dokumentu na granicy słów
  do 200 znaków. Jeden kandydat → `DELETE`; kilku → nic nie usuwa, ostrzeżenie, krok zostaje zaległy; zero przed
  `listed_by` → krok zostaje; zero po `listed_by` → krok rozliczony z `logger.warning`, że upload mógł zostać na
  koncie (z liczbą importów w oknie, bez tytułu i tekstu).
- Zaległe sprzątanie jest trwałe w prywatnym `session.json` (`restore`, `documents`: `pressed_at`, `listed_by`,
  `titles`, `read_id`): `prepare_account` i `upload` zapisują je przed zmianą konta, gospodarz po każdym sprzątaniu,
  `load_cleanup` wczytuje je raz na gospodarza. Czas zegarowy zachowuje okno wgrania po restarcie procesu i komputera.
- Błąd próby zamyka tylko jej kartę. Anulowanie, timeout i niedostępność (`_SUSPECT_ERRORS`) oznaczają przeglądarkę
  jako podejrzaną; restart następuje przy otwieraniu karty, gdy żadne inne nagranie nie trwa. Martwy Chrome
  (`alive == False`) startuje od nowa przy następnej próbie.

## Pułapki

- Konto trzyma na urządzeniu najwyżej 2 strumienie naraz (pomiar w AniShift): przy 3 i 5 nowy strumień zamyka
  starszy, a ta karta stoi do `STALL_S`. Dlatego `MAX_PARALLEL_DOCUMENTS` = 2; podniesienie tylko po nowym pomiarze na
  żywym koncie. Otwarcie i zamknięcie strumienia logują `ElevenReader stream opened/closed` z liczbą odebranych
  znaków.
- Brak retry w transporcie. Ponowne „Play” (do 3) i pętla dołączania do CDP to czynności jednej próby; ponowienia
  całego dokumentu robi `reading.py`.
- Błąd Playwright przy starcie sterownika, dołączaniu i przygotowaniu kontekstu (`ChromeSession._attach`) staje się
  `unavailable_error`, więc `sign_in` kończy się `FAILED` zamiast wisieć.
- Każde wywołanie strony w próbie (także `set_page_speed`, `press_play`, `check_page_speed`, `player_state`) idzie
  przez `unless_cancelled`, więc anulowanie nie czeka na limit Playwright; `evaluate` nie ma własnego limitu.
- Blokadę startu, Chrome, kartę i nagrywanie próby ogranicza `request.deadline_s` (`within_deadline`): po jego
  upływie próba kończy się `TtsTimeoutError` (przejściowy), a sprzątanie i zamknięcie karty biegną w `finally` jak po
  każdym błędzie. Ten termin jest jedynym górnym limitem próby; poza nim są czekanie w bramce głosu (ogranicza je
  tylko anulowanie) i końcowe sprzątanie (każdy krok `CLEANUP_STEP_TIMEOUT_S`).
- Token, `read_id`, adres WebSocketu i tekst dokumentu nie trafiają do logów ani wyjątków. Token i adres
  WebSocketu nie trafiają też do plików. Prywatny `session.json` (katalog domowy z `restrict_directory`) ma tylko
  `signed_in`, `checked_at`, `restore` (głos i tempo konta) i `documents` (czasy, `read_id` wyłącznie do sprzątania
  oraz skróty SHA-256 prefiksów tytułu). Skróty nie są jawnym tekstem, ale słownikiem da się je odwrócić słowo po
  słowie. Adres strumienia jest sprawdzany w pamięci.
- Część pusta po neutralizacji, równa `LINE_SEPARATOR` albo z `<break` to `TtsInputError` z `validate_part`;
  `reading.py` woła ją dla każdej części przed grupowaniem, a `synthesize_document` dla każdej części przed
  przeglądarką. `<break` jest odrzucany także przy `request.tags`, bo psuje granice części.
- `request.tags` przepuszcza nawiasy kwadratowe do serwera jako znaczniki v4 (`document_text` i `part_spans` z
  `tags=True`); domyślnie `[` i `]` zamieniają się na `(` i `)`.
- Błąd zapisu nagrania (`OSError`) zatrzymuje `StreamRecorder`; `_record` w następnym takcie rzuca
  `TtsClipValidationError` z `error_class` i `errno`, bez ścieżki.
- Pierwsza ramka wysyłana z `listening_speed` ≠ 1 oznacza model v2 → błąd przejściowy.
- Wylogowanego gościa biblioteka przekierowuje na `/reader/sign-up` (przyciski „Sign up with Google/Apple/email”,
  „Sign in” nie jako przycisk); `open_library` rozpoznaje to po adresie i przyciskach „Sign up”. Status 402 jako brak
  kredytów jest niepotwierdzonym założeniem.
- `GET reads` (zmierzone) zwraca `{"reads": [...], "has_more", "next_cursor", "last_sort_id"}`; nowy
  upload był na pierwszej stronie. Kod czyta tylko ją, bez paginacji. Założenie: kolejność od najnowszych, a upload
  bez `read_id` szuka się zwykle w tym samym przebiegu, minuty po wgraniu (sprzątanie po anulowaniu, następna próba,
  `close()`). Po dłuższej przerwie dokument może być poza pierwszą stroną; wtedy krok rozlicza się z ostrzeżeniem,
  a nie po cichu. Brak listy `reads` zostawia krok `delete_orphan` zaległym (widocznym w `edp doctor`), nigdy nie
  rozlicza go po cichu.
- `char_count` z odpowiedzi uploadu jest obowiązkowy; bez niego próba kończy się błędem przejściowym.
- Serwer potrafi nie wypowiedzieć części (np. strzępu szyldu `j g`): jej znaki mają zerowy czas, a `part_spans` zwraca
  dla niej pusty `PartTiming` zamiast błędu, więc odpada tylko ta część. Inna liczba lub tekst części i odwrócony
  czas pozostają `TtsClipValidationError` całego nagrania.
- Serwer potrafi też oddać porcję z pełnym tekstem i alignmentem, ale prawie bez dźwięku (ok. 1 ms na znak, bez
  `notice`). `StreamRecorder` oznacza porcję jako `silent`, gdy ma co najmniej `SILENT_CHUNK_MIN_LETTERS` liter (`\w`
  po usunięciu tagów `<...>`) i mniej niż `SILENT_CHUNK_MS_PER_LETTER` ms ramek MP3 na literę, i loguje ostrzeżenie
  z indeksem porcji, liczbą liter i ms dźwięku, bez tekstu. Każda część nachodząca na taką porcję dostaje w
  `part_spans` pusty `PartTiming`; ponowny odczyt w mniejszych dokumentach robi `reading.py`. Krótszej porcji reguła
  nie ocenia.
