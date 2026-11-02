# Możliwości: co zwraca ElevenReader i co z tego zbudujemy

Stan na 2026-10-18. Źródła: `workspace/output/metadata_dump.json` (jedna sesja: upload, otwarcie, odtwarzanie krótkiego dokumentu testowego), nagrania `MS2_001`–`MS2_014`, `demo-narration`, logi `auto*.log`, `src/timestamps.py`, `src/auto.py` oraz pomiary na żywo z 2026-10-17/18. Przy każdej liczbie zaznaczam, czy to pomiar, czy szacunek.

## W skrócie

- Z audio dostajemy czas każdego znaku. To wystarcza na napisy zdaniowe, karaoke słowne i cięcie jednego MP3 na klipy pod linijki SRT.
- Kredyty liczą się od znaków, które serwer faktycznie czyta, łącznie z wstawianymi przez niego tagami `<break .../>`. W prozie tagi to około 12% rachunku; w tekście pociętym na krótkie akapity (np. SRT) nawet 50%.
- `current_credits` ma cztery miejsca po przecinku, czyli dokładność do jednego znaku. Różnica przed i po nagraniu to dokładny koszt.
- Głos v4 (Piotr Fronczewski, polski, 1x) czyta średnio 933 znaki na minutę audio. 1 h audio kosztuje około 5,6 kredytu i pobiera się w około 13 minut.
- 262 kredyty to około 47 h audio, czyli około 10 h pobierania.
- Import z `.txt` daje zawsze jeden rozdział (`Chapter 0`). Rozdziały do audiobooka trzeba więc wyznaczyć samemu: plik na rozdział albo nagłówki w tekście.

## 1. Co zwraca serwer

Zrzut ma 51 zapytań HTTP i 8 ramek WebSocket. Pominąłem odpowiedzi bez treści (miniatury głosów, `reddit/capi`, `simple-html`, którego treści zrzut nie zapisał) i wszystko, co oznaczono jako `<redacted>`.

### WebSocket `wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{read_id}`

| Kierunek | Pole                                       | Co znaczy                                                                                                                                                        | Przydatność |
| -------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| klient   | `listening_speed`                          | prędkość z ustawień ElevenReader (w zrzucie 3.1); wpływa na wybór modelu: ~2,65–3,1 dawało v2, 1.0 dawało v4                                                     | wysoka      |
| klient   | `position`                                 | offset znaku, od którego serwer ma czytać (0 = początek)                                                                                                         | średnia     |
| klient   | `listening_position`                       | okresowy raport pozycji odtwarzacza w znakach (149, potem 167 – dokładnie tyle znaków już przyszło)                                                              | średnia     |
| klient   | `stream_id`                                | UUID strumienia, serwer odsyła go jako `streamId`                                                                                                                | żadna       |
| serwer   | `type: "config"`, `maxReadingSpeed: "4.0"` | pierwsza ramka: maksymalna prędkość czytania, jaką serwer dopuszcza                                                                                              | średnia     |
| serwer   | `audio`                                    | fragment MP3 w base64 (od ~2 KB do ~230 KB w ramce)                                                                                                              | wysoka      |
| serwer   | `alignment.chars`                          | znaki czytane w tej paczce, łącznie z tagami `<break time="0.6s"/>` i końcowym `<break time="2s"/>`; tekst wraca dosłownie (liczby, skróty typu „np.” bez zmian) | wysoka      |
| serwer   | `alignment.charStartTimesMs`               | start każdego znaku w ms, liczony od początku paczki                                                                                                             | wysoka      |
| serwer   | `alignment.charDurationsMs`                | czas trwania każdego znaku w ms                                                                                                                                  | wysoka      |
| serwer   | `isFinal`                                  | `true` w ostatniej, pustej ramce: koniec dokumentu                                                                                                               | wysoka      |

Dwie obserwacje z danych:

- Suma znaków ze wszystkich paczek (169) jest równa `char_count` dokumentu, a `current_credits` spadło o 0,0169. Tagi `<break>` liczą się więc i do `char_count`, i do rachunku (pomiar ze zrzutu).
- Tag `<break time="0.6s"/>` nie daje w alignmencie 0,6 s ciszy. W v4 jego znaki mają łącznie kilka–kilkadziesiąt ms, a przerwa między słowami po obu stronach tagu wynosi w medianie 0,32 s. Zwykła przerwa między zdaniami to 0,28–0,30 s (pomiar na `MS2_011` i `MS2_012`). Końcowy `<break time="2s"/>` rozkłada 2 s równo na swoje 18 znaków (po ~111 ms).

### HTTP `api.elevenlabs.io/v1/reader/...`

| Źródło                                        | Pole                                                      | Co znaczy                                                                                               | Przydatność |
| --------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------- |
| `POST reads/add/v2`, `GET reads/{id}`         | `read_id`, `canonical_read_id`                            | identyfikator dokumentu (`u:...`), potrzebny w adresie WebSocketu                                       | wysoka      |
| j.w.                                          | `char_count`, `word_count`                                | długość tekstu do przeczytania razem z tagami `<break>`; równa liczbie znaków rozliczanej w kredytach   | wysoka      |
| j.w.                                          | `chapters[]`                                              | `chapter_name`, `char_count`, `word_count`, `starting_char_offset`; dla `.txt` zawsze jeden `Chapter 0` | wysoka      |
| j.w.                                          | `chapters[].duration_seconds`, `audio_duration_seconds`   | dla własnych importów `null`; długość audio trzeba policzyć samemu                                      | żadna       |
| j.w.                                          | `language`                                                | wykryty język tekstu; nowy upload: `"Polish"`, stare dokumenty w bibliotece: `"Polski"`                 | średnia     |
| j.w.                                          | `creation_status`, `creation_progress`                    | stan przetwarzania po imporcie (`finished`, `1.0`)                                                      | średnia     |
| j.w.                                          | `html_checksum`                                           | skrót treści; pozwala wykryć, że ten sam tekst już jest w bibliotece                                    | średnia     |
| j.w.                                          | `last_listened_char_offset`                               | pozycja wznowienia w znakach                                                                            | średnia     |
| j.w.                                          | `original_file_type`, `from_user_import`, `audio_type`    | `text/plain`, `true`, `tts`                                                                             | żadna       |
| j.w.                                          | `title`, `description`, `read_slug`                       | tytuł i opis wzięte z pierwszego zdania tekstu                                                          | żadna       |
| j.w.                                          | `use_drm`, `is_payable`, `isbn`, `genre`, `narrators`...  | pola katalogu książek; dla importów puste                                                               | żadna       |
| `GET reads?page_size=100`                     | `reads[]`, `has_more`, `last_sort_id`                     | lista biblioteki (100 dokumentów, wszystkie `.txt`, jednorozdziałowe)                                   | średnia     |
| `GET reads/changes`                           | `reads`, `deleted_read_ids`                               | zmiany od podanego czasu (w zrzucie 717 usuniętych identyfikatorów)                                     | żadna       |
| `GET customer`                                | `plan`, `billing_period`                                  | `ultra`, `annual`                                                                                       | średnia     |
| j.w.                                          | `current_credits`                                         | saldo z dokładnością 0,0001 kredytu (= 1 znak); 262,7641 przed i 262,7472 po teście                     | wysoka      |
| j.w.                                          | `next_credit_date_unix`                                   | termin najbliższego doładowania                                                                         | wysoka      |
| j.w.                                          | `premium_books_credits`                                   | kredyty na płatne tytuły z Explore (120), nie na własne importy                                         | żadna       |
| `GET products/one-time-page/v2`               | `current_credits`, `current_hours`, `current_minutes`     | 263 / 44 / 2628; `current_minutes` = kredyty × 10 (szacunek ElevenReadera dla 1x)                       | średnia     |
| j.w.                                          | `subtitle`                                                | opis planu: „Up to 24 hours/day of text to audio for your own imports (estimated at 1x speed)”          | średnia     |
| j.w.                                          | `one_time_products[]`                                     | dokupienie 10 h za 5 USD i 20 h za 10 USD                                                               | średnia     |
| `GET user_config`                             | `playback_speed_rate`                                     | prędkość z ustawień (3.1); to ona trafia do `listening_speed`                                           | wysoka      |
| j.w.                                          | `voice_expressiveness`, `default_voice_id`                | `expressive` i domyślny głos (trafiają do adresu WebSocketu)                                            | średnia     |
| j.w.                                          | `feature_flags`                                           | m.in. `device_rate_limit_enabled`, `ip_ban_check_enabled`, `stream_read_v2_enabled`; App Check aktywny  | średnia     |
| `GET voices`, `GET voices/{id}`               | `voice_id`, `name`, `language`, `category`, `preview_url` | 45 głosów: 38 `en`, 3 `pl`, 2 `de`, po 1 `es` i `hu`; Fronczewski ma kategorię `famous`                 | średnia     |
| `GET /v1/user`                                | `subscription.*`                                          | subskrypcja ElevenLabs (platforma twórcza, `free`, 10 000 znaków), osobna od ElevenReadera              | żadna       |
| pozostałe (`notifications`, `collections`...) | różne                                                     | interfejs aplikacji (też `messages`, `bookmarks`, `referrals`, `api/version`)                           | żadna       |

### Co z tego zapisuje narzędzie

| Plik                 | Zawartość                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------- |
| `<name>.mp3`         | sklejone fragmenty `audio`                                                                                    |
| `<name>.txt`         | sklejone `alignment.chars`, z tagami `<break>`                                                                |
| `<name>.align.jsonl` | linia na paczkę: `offset_ms` (pozycja paczki w nagraniu), `chars`, `start_ms`, `dur_ms`, opcjonalnie `resume` |
| `<name>.srt`         | zdania; granica na `.!?…` przed nowym zdaniem i na każdym tagu `<break>`                                      |
| `<name>.json`        | `sentences[]` z `text`, `start`, `end` (s) i `words[]` z czasem każdego słowa                                 |

Przykładowa linia `align.jsonl` (z `demo-narration`, skrócona):

```json
{"offset_ms": 63686.5, "chars": [" ", "<", "b", "r", "e", "a", "k"], "start_ms": [0, 111, 223, 335, 446, 558, 670], "dur_ms": [111, 112, 112, 111, 112, 112, 112]}
```

Na próbce `demo-narration` (1,09 min) wychodzi 19 zdań, a pierwsze słowo ma czasy `0.000–0.674 s`. W rozdziałach `MS2_011` i `MS2_012` średnie zdanie ma 60 znaków i trwa 4,1–4,2 s, a tempo to 127–129 słów na minutę.

## 2. Co można z tego zbudować

Nakład pracy: S – do dnia, M – kilka dni, L – ponad tydzień.

| Pomysł                                                    | Potrzebne dane                                                                | Co już jest gotowe                                                                                                                                                  | Nakład | Ryzyko                                                                                                                   |
| --------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------ |
| Napisy zdaniowe (`.srt`)                                  | `alignment` + offset paczki                                                   | gotowe: `timestamps.py`                                                                                                                                             | –      | niskie; podział zdań to heurystyka (skróty, dialogi)                                                                     |
| Karaoke słowne (np. `.ass` z `\k`, `.vtt`)                | czasy słów z `<name>.json`                                                    | dane gotowe, brak tylko eksportu do formatu                                                                                                                         | S      | niskie                                                                                                                   |
| Audiobook z rozdziałami                                   | podział na rozdziały: plik na rozdział albo nagłówki w tekście + czasy znaków | `auto.py` nagrywa plik po pliku (tak powstały `MS2_001`–`014`); `mp3_duration_ms` liczy długości                                                                    | S–M    | dla `.txt` serwer daje jeden `Chapter 0`; czy EPUB daje wiele `chapters[]` z `starting_char_offset` – niesprawdzone      |
| Znaczniki rozdziałów w MP3 (ID3 `CHAP`/`CTOC`) lub `.cue` | początek każdego rozdziału w ms                                               | długości z `mp3_duration_ms`; offset znaku → ms z `align.jsonl`                                                                                                     | S      | niskie; nie każdy odtwarzacz czyta `CHAP` (alternatywa: `.m4b`, wymaga ffmpeg)                                           |
| Lektor do filmu z SRT                                     | linijki SRT; czas pierwszego i ostatniego znaku każdej linijki                | AniShift: `split_subtitles`, `plan_timeline` (tryb `SOURCE_TIMES`, przesuwanie przy nakładaniu), miks; klipy jako `TimedAudioClip`; tu: czasy znaków i `mp3_cut_ms` | M      | mowa dłuższa niż okno napisu; zlewanie intonacji linijek; tagi `<break>` podnoszą koszt o ~50%; prawa do głosu `famous`  |
| Estymator czasu i kosztu przed nagraniem                  | `char_count` z `reads/add/v2` (albo lokalne liczenie + prognoza tagów)        | `auto.py` już odczytuje `char_count`                                                                                                                                | S      | prognoza czasu zależy od modelu i obciążenia serwera                                                                     |
| Monitor zużycia kredytów                                  | `customer.current_credits` przed i po, `next_credit_date_unix`                | nic; to jedno zapytanie przed i po nagraniu (odczyt danych, które strona i tak pobiera)                                                                             | S      | niskie; pole jest wewnętrzne i może zniknąć                                                                              |
| Wykrywanie języka i dobór głosu                           | `language` dokumentu, `voices[].language`                                     | dane przychodzą przy uploadzie                                                                                                                                      | S      | niespójny format (`Polish` / `Polski`); tylko 3 głosy `pl`                                                               |
| Kontrola kompletności                                     | `char_count` kontra suma odebranych znaków                                    | gotowe w `auto.py` (`Text received: X/Y`, ostrzeżenie o nadmiarze)                                                                                                  | –      | po rozłączeniu bywa nadmiar (51811/51479, 41568/41415) albo brak (96411/96937); potrzebna tolerancja i porównanie tekstu |
| Wyszukiwanie w audio po tekście                           | `<name>.txt` + czasy słów                                                     | dane gotowe                                                                                                                                                         | S      | niskie                                                                                                                   |
| E-book czytany na głos (EPUB 3 Media Overlays)            | czasy zdań lub słów, tekst źródłowy                                           | dane gotowe                                                                                                                                                         | L      | mapowanie na strukturę EPUB, testy w czytnikach                                                                          |

Lektor z SRT da się zrobić na dwa sposoby. Za każdym razem wysyłamy jeden dokument i tniemy jedno MP3, bo czasy znaków wskazują początek i koniec każdej linijki:

- Wariant A: każda linijka jako osobny akapit. Serwer wstawi między nie `<break time="0.6s"/>`, co daje wyraźne granice i oddech, ale kosztuje około 21 znaków na linijkę.
- Wariant B: linijki w jednym akapicie, granice z offsetów znaków. Jest o około 35% taniej, ale sąsiednie linijki mogą zlać się intonacyjnie.

## 3. Kalkulator

Założenia (v4, głos Piotr Fronczewski, polski, `listening_speed` 1.0):

```text
R  = 933 znaki rozliczane na minutę audio   (pomiar: 12 rozdziałów, 588 067 znaków, 630,5 min; zakres 911–961; rodzic: ~945)
T  = 4,6x czasu rzeczywistego               (pomiar: rozdział 12 – 80,5 min w 17,5 min; rozdział 11 – 109 min w 23 min)
K  = 10 000 znaków na kredyt                 (pomiar: 3 sesje + zrzut, 169 znaków = 0,0169 kredytu)
br = 21 znaków na tag między akapitami       (" <break time=\"0.6s\"/>" ze spacją), + 20 znaków na końcu dokumentu
p  = 0,6 s pauzy na tag                      (założenie zadania; pomiar w alignmencie: ~0,32 s, więc to górna granica)

audio_min    = znaki / R
kredyty      = znaki / K
pobieranie   = audio_min / T  (+ ~1 min na upload i otwarcie dokumentu)
znaki_z_h    = h × 60 × R
```

W prozie (ta książka) tagi to 11,8% znaków rozliczanych, czyli około +13% do czystego tekstu. Stawka R już je zawiera. Czasy pobierania w tabeli nie obejmują ~1 min na upload i otwarcie dokumentu.

| Scenariusz                   | Znaki rozliczane                | Audio             | Kredyty | Pobieranie v4 (4,6x) | Pobieranie v2 (~4x / do 13x) |
| ---------------------------- | ------------------------------- | ----------------- | ------- | -------------------- | ---------------------------- |
| 1 h audio                    | 60 × 933 = 55 980               | 60 min            | 5,6     | ~13 min              | ~15 min / ~5 min             |
| Audiobook 10 h               | 559 800                         | 600 min           | 56      | ~2 h 10 min          | ~2 h 30 min / ~46 min        |
| Rozdział 50 000 znaków       | 50 000 (z tagami)               | 53,6 min          | 5,0     | ~12 min              | ~13 min / ~4 min             |
| j.w., 50 000 czystego tekstu | ~56 700 (+13% tagów)            | ~60,8 min         | 5,7     | ~13 min              | ~15 min / ~5 min             |
| SRT 300 linijek, wariant A   | 12 000 + 299 × 21 + 20 ≈ 18 300 | ~15,8 min         | 1,8     | ~3,5 min             | ~4 min / ~1 min              |
| SRT 300 linijek, wariant B   | ~12 000                         | ~12,9 min         | 1,2     | ~3 min               | ~3 min / ~1 min              |
| 262 kredyty                  | 2 620 000                       | ~2 808 min ≈ 47 h | 262     | ~10 h 10 min         | ~11 h 40 min / ~3 h 40 min   |

Jak liczyłem SRT:

- Linijka ma średnio 40 znaków, więc 300 linijek to 12 000 znaków czystego tekstu.
- Mowa: 12 000 / 933 ≈ 12,9 min, czyli około 64 ms na znak i około 2,6 s na linijkę.
- Wariant A dokłada 299 pauz × 0,6 s ≈ 3,0 min, razem około 15,8 min. Przy zmierzonych 0,32 s byłoby to około 14,5 min.
- Wariant A kosztuje około 50% więcej kredytów niż B, bo tagi stanowią około 34% znaków rozliczanych.

Kolumna v2 to tylko czas pobierania. Tempa mowy v2 (znaków na minutę) nie zmierzyłem osobno, więc audio i kredyty dla v2 przyjmuję jak dla v4.

Dla porównania ElevenReader sam szacuje 10 min na kredyt (`current_minutes` = kredyty × 10, czyli 1000 znaków na minutę). Dla 262 kredytów wychodzi mu około 44 h, a nam z pomiaru około 47 h.

## 4. Ograniczenia i ryzyka

- **Regulamin.** ElevenReader nie ma oficjalnego eksportu audio. Prohibited Use Policy ElevenLabs (2026-10-09) zakazuje automatycznych narzędzi do ekstrakcji, a o to właśnie chodzi w tym projekcie. Ryzyko blokady konta jest realne: flagi `device_rate_limit_enabled` i `ip_ban_check_enabled` są włączone, App Check aktywny (`app_check_bypass_enabled: false`). Nie obchodzimy tych zabezpieczeń i nie podrabiamy protokołu. Narzędzie tylko odczytuje to, co strona i tak dostaje w prawdziwym Chrome.
- **Prawa do głosu.** Fronczewski ma w katalogu kategorię `famous` („Iconic Voice”). Publikowanie nagrań, a zwłaszcza dubbing filmów jego głosem, może wymagać osobnej zgody. Na prywatny odsłuch tego problemu nie ma.
- **Wewnętrzne API.** Endpointy i format ramek są nieudokumentowane i mogą zmienić się bez ostrzeżenia: `stream/v2` stoi za flagą `stream_read_v2_enabled`, a `api/version` może wymusić odświeżenie.
- **Model zależy od ustawień.** Model wynika z `listening_speed` w ustawieniach ElevenReadera: przy 1.0 jest v4 (expressive), przy ~3x szybszy v2. Przyspieszenie po naszej stronie (64x) nie zmienia ani modelu, ani tempa mowy. Strona startuje strumień z `playback_speed_rate` z `user_config` zaraz po wczytaniu dokumentu, więc zmiana prędkości w otwartym odtwarzaczu przychodzi za późno. `auto.py` ustawia 1.0 przez `POST user_config` przed otwarciem dokumentu i przerywa nagranie, gdy pierwsza ramka klienta ma inne `listening_speed`.
- **Przepustowość ogranicza serwer.** Dostajemy około 4–5x czasu rzeczywistego, sporadycznie do 13x. 16x, 32x i 64x po naszej stronie nic nie zmieniają.
- **Limit kredytów.** Zgodnie z deklaracją planu to do 24 h audio na dobę, czyli około 144 kredyty przy szacunku 10 min na kredyt. Saldo doładowuje się w `next_credit_date`. Jak ten limit dobowy ma się do salda 262 kredytów, nie sprawdziłem.
- **Tagi `<break>` są płatne:** około 12% w prozie i do ~35% przy krótkich akapitach. Rzeczywista pauza wynosi około 0,3 s, a nie 0,6 s.
- **Rozdziały.** Import `.txt` daje jeden rozdział, a długość audio (`duration_seconds`, `audio_duration_seconds`) zostaje `null`. Struktura rozdziałów i czasy są po naszej stronie.
- **Rozłączenia.** Po wznowieniu pierwsze zdanie może przyjść drugi raz. Narzędzie to obsługuje, ale zgodność `char_count` z liczbą odebranych znaków nie zawsze jest dokładna, więc kontrola kompletności potrzebuje tolerancji.
