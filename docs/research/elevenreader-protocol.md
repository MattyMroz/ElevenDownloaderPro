# Protokół ElevenReadera: strumień, API, koszty i granice

Notatka opisuje, co ElevenReader wysyła i przyjmuje przez WebSocket i HTTP, ile kosztuje nagranie i gdzie leżą granice
konta; pomiary z 17–26 października 2026 r., limit strumieni z testu AniShift z 31 października 2026 r.

Źródła: zrzut `workspace/output/metadata_dump.json` (jedna sesja: upload, otwarcie i odtwarzanie krótkiego dokumentu
testowego), nagrania `MS2_001`–`MS2_014` i `demo-narration`, logi nagrań, pomiary na żywo z 17–19 i 26 października
2026 r. oraz test sieciowy AniShift (`docs/work/11-elevenreader-tts/outcomes/02-parallel-documents.md` na `origin/main`).
Przy każdej liczbie zaznaczam, czy to pomiar, czy szacunek.

## W skrócie

- Audio przychodzi przez WebSocket jako MP3 128 kb/s, 44,1 kHz, w porcjach. Razem z audio przychodzi tekst porcji
  i czas każdego znaku: start i długość w milisekundach.
- Kredyty liczą się od znaków, które serwer faktycznie czyta, łącznie z tagami `<break .../>`, które sam wstawia między
  akapitami. W prozie tagi to około 12% rachunku, w tekście pociętym na krótkie akapity (np. SRT) około 34%, co
  podnosi koszt o około 50% względem tego samego tekstu w jednym akapicie.
- `current_credits` ma cztery miejsca po przecinku, czyli dokładność do jednego znaku. Różnica przed i po nagraniu to
  dokładny koszt.
- Głos v4 (Piotr Fronczewski, polski, 1x) czyta średnio 933 znaki na minutę audio. 1 h audio kosztuje około 5,6
  kredytu i pobiera się w około 13 minut.
- Model v4 serwer daje przy prędkości konta 1x, przy około 3x przechodzi na v2. Model ustala się przy starcie
  strumienia i nie zmienia do końca.
- Jeden strumień daje 4,5–5,5x czasu rzeczywistego. Konto trzyma na urządzeniu najwyżej 2 strumienie naraz.
- Import z `.txt` daje zawsze jeden rozdział (`Chapter 0`).

## 1. WebSocket `wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{read_id}`

Zrzut ma 51 zapytań HTTP i 8 ramek WebSocket. Pominąłem odpowiedzi bez treści (miniatury głosów, `reddit/capi`,
`simple-html`, którego treści zrzut nie zapisał) i wszystko, co oznaczono jako `<redacted>`.

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

- Suma znaków ze wszystkich paczek (169) jest równa `char_count` dokumentu, a `current_credits` spadło o 0,0169. Tagi
  `<break>` liczą się więc i do `char_count`, i do rachunku (pomiar ze zrzutu).
- Tag `<break time="0.6s"/>` nie daje w alignmencie 0,6 s ciszy. W v4 jego znaki mają łącznie kilka–kilkadziesiąt ms,
  a przerwa między słowami po obu stronach tagu wynosi w medianie 0,32 s. Zwykła przerwa między zdaniami to 0,28–0,30 s
  (pomiar na `MS2_011` i `MS2_012`). Końcowy `<break time="2s"/>` rozkłada 2 s równo na swoje 18 znaków (po ~111 ms).

## 2. HTTP `api.elevenlabs.io/v1/reader/...`

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

Prędkość konta zmienia się przez `POST user_config` z polem `playback_speed_rate`.

## 3. Pomiary

### Przepustowość

- Jeden strumień pobiera audio około 4,5–5,5 razy szybciej niż czas odtwarzania (pomiar z 17–18 października). Na
  rozdziałach v4 wyszło 4,6x: rozdział 12 to 80,5 min audio w 17,5 min, rozdział 11 to 109 min w 23 min. Przy v2
  zwykle około 4x, sporadycznie do 13x.
- Przyspieszenie strony powyżej 16x nic nie daje: 16x, 32x i 64x dają to samo, bo ogranicza serwer. Przyspieszenie po
  stronie przeglądarki nie zmienia ani modelu, ani tempa mowy.

### Strumienie równoległe

Dwa pomiary różnią się przy dwóch strumieniach naraz:

- 19 października 2026 r.: otwarcie nowego strumienia zamykało starszy. Przy 4 kartach zamknęły się 2, przy 2 kartach
  jedna. Wszystkie karty mają ten sam identyfikator urządzenia.
- 31 października 2026 r. (test sieciowy AniShift, dokumenty po ok. 8 000 znaków, starty co 14–17 s): przy 2
  dokumentach naraz 3 przebiegi na 3 przeszły bez zamkniętego strumienia; przy 3 i 5 nowy strumień zamyka starszy.
  Wniosek AniShift: konto trzyma na urządzeniu najwyżej 2 strumienie naraz.

Późniejszy test jest podstawą limitu 2 dokumentów naraz w silniku.

### Model głosu

- Prędkość czytania 1x daje model v4. Przy około 3x (obserwowane 2,65–3,1) serwer przechodzi na starszy v2.
- Strona otwiera strumień z prędkością zapisaną na koncie (`playback_speed_rate`) zaraz po wczytaniu dokumentu, a model
  zostaje do końca strumienia. Zmiana prędkości w otwartym odtwarzaczu przychodzi za późno, więc 1x trzeba ustawić na
  koncie przed otwarciem dokumentu. Pierwsza ramka klienta (`listening_speed`) pokazuje, z jaką prędkością ruszył
  strumień.
- Dowód: 26 października 2026 r. nagranie `SS_3201-3225` poszło w całości w v2, bo konto miało 3x.
- Konto ma ustawioną najbardziej ekspresywną barwę (`voice_expressiveness: expressive`).

### Pamięć serwera

Ten sam tekst nagrany drugi raz przychodzi z pamięci serwera: około 58 razy szybciej i bez kredytów.

### Czasy znaków

- Czasy znaków wyprzedzają faktyczną mowę o około 0,3 s.
- W rozdziałach `MS2_011` i `MS2_012` średnie zdanie ma 60 znaków i trwa 4,1–4,2 s, a tempo to 127–129 słów na minutę.

## 4. Koszty

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

W prozie tagi to 11,8% znaków rozliczanych, czyli około +13% do czystego tekstu. Stawka R już je zawiera. Czasy
pobierania w tabeli nie obejmują ~1 min na upload i otwarcie dokumentu.

| Scenariusz                   | Znaki rozliczane                | Audio             | Kredyty | Pobieranie v4 (4,6x) | Pobieranie v2 (~4x / do 13x) |
| ---------------------------- | ------------------------------- | ----------------- | ------- | -------------------- | ---------------------------- |
| 1 h audio                    | 60 × 933 = 55 980               | 60 min            | 5,6     | ~13 min              | ~15 min / ~5 min             |
| Audiobook 10 h               | 559 800                         | 600 min           | 56      | ~2 h 10 min          | ~2 h 30 min / ~46 min        |
| Rozdział 50 000 znaków       | 50 000 (z tagami)               | 53,6 min          | 5,0     | ~12 min              | ~13 min / ~4 min             |
| j.w., 50 000 czystego tekstu | ~56 700 (+13% tagów)            | ~60,8 min         | 5,7     | ~13 min              | ~15 min / ~5 min             |
| SRT 300 linijek, wariant A   | 12 000 + 299 × 21 + 20 ≈ 18 300 | ~15,8 min         | 1,8     | ~3,5 min             | ~4 min / ~1 min              |
| SRT 300 linijek, wariant B   | ~12 000                         | ~12,9 min         | 1,2     | ~3 min               | ~3 min / ~1 min              |
| 262 kredyty                  | 2 620 000                       | ~2 808 min ≈ 47 h | 262     | ~10 h 10 min         | ~11 h 40 min / ~3 h 40 min   |

Warianty SRT:

- Wariant A: każda linijka jako osobny akapit. Serwer wstawia między nie `<break time="0.6s"/>`, około 21 znaków na
  linijkę. Wariant B: linijki w jednym akapicie, granice z offsetów znaków; sąsiednie linijki mogą zlać się
  intonacyjnie.
- Linijka ma średnio 40 znaków, więc 300 linijek to 12 000 znaków czystego tekstu. Mowa: 12 000 / 933 ≈ 12,9 min,
  czyli około 64 ms na znak i około 2,6 s na linijkę.
- Wariant A dokłada 299 pauz × 0,6 s ≈ 3,0 min, razem około 15,8 min. Przy zmierzonych 0,32 s byłoby to około 14,5 min.
- Wariant A kosztuje około 50% więcej kredytów niż B, bo tagi stanowią około 34% znaków rozliczanych.

Kolumna v2 to tylko czas pobierania. Tempa mowy v2 (znaków na minutę) nie zmierzyłem osobno, więc audio i kredyty dla
v2 przyjmuję jak dla v4.

ElevenReader sam szacuje 10 min na kredyt (`current_minutes` = kredyty × 10, czyli 1000 znaków na minutę). Dla 262
kredytów wychodzi mu około 44 h, a z pomiaru około 47 h.

## 5. Ograniczenia i ryzyka

- **Regulamin.** ElevenReader nie ma oficjalnego eksportu audio. Prohibited Use Policy ElevenLabs (2026-10-09) zakazuje
  automatycznych narzędzi do ekstrakcji, a o to właśnie chodzi w tym projekcie. Ryzyko blokady konta jest realne: flagi
  `device_rate_limit_enabled` i `ip_ban_check_enabled` są włączone, App Check aktywny
  (`app_check_bypass_enabled: false`). Nie obchodzimy tych zabezpieczeń i nie podrabiamy protokołu; odczytujemy to, co
  strona i tak dostaje w prawdziwym Chrome.
- **Prawa do głosu.** Fronczewski ma w katalogu kategorię `famous` („Iconic Voice”). Publikowanie nagrań, a zwłaszcza
  dubbing filmów jego głosem, może wymagać osobnej zgody. Na prywatny odsłuch tego problemu nie ma.
- **Wewnętrzne API.** Endpointy i format ramek są nieudokumentowane i mogą zmienić się bez ostrzeżenia: `stream/v2` stoi
  za flagą `stream_read_v2_enabled`, a `api/version` może wymusić odświeżenie.
- **Limit kredytów.** Zgodnie z deklaracją planu to do 24 h audio na dobę, czyli około 144 kredyty przy szacunku 10 min
  na kredyt. Saldo doładowuje się w `next_credit_date`. Jak ten limit dobowy ma się do salda 262 kredytów, nie
  sprawdziłem.
- **Rozdziały.** Import `.txt` daje jeden rozdział, a długość audio (`duration_seconds`, `audio_duration_seconds`)
  zostaje `null`. Struktura rozdziałów i czasy są po naszej stronie. Czy EPUB daje wiele `chapters[]` ze
  `starting_char_offset`, nie sprawdzono.
- **Rozłączenia.** Po wznowieniu pierwsze zdanie może przyjść drugi raz. Liczba odebranych znaków nie zawsze zgadza się
  z `char_count`: bywa nadmiar (51811/51479, 41568/41415) albo brak (96411/96937), więc kontrola kompletności potrzebuje
  tolerancji i porównania tekstu.
