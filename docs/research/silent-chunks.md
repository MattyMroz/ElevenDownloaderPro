# Cicha porcja: ElevenReader zwraca tekst bez mowy

Notatka opisuje porcje strumienia, w których ElevenReader oddaje pełny tekst prawie bez dźwięku: objaw, wykrywanie i naprawę; stan na 2026-11-01.

Źródła: nagrania `workspace/output/` (MS3_002–MS3_009, SS_3201-3225, SS_3201-3225_v2, testy `T*`, `P*`), dwa nagrania `MS3_009` (`bad_MS3_009/`, `run2_MS3_009/`), logi nagrań i kod dawnych skryptów ElevenDownloaderPro (commit `a55aecd`) oraz silnik `AniShift/anishift/services/tts/engines/elevenreader/` (commit `f595718`). Wszystkie liczby to pomiary, chyba że zaznaczono inaczej.

## W skrócie

- Serwer ElevenReadera potrafi oddać porcję z pełnym tekstem i poprawnym `alignment`, ale z prawie zerowym dźwiękiem: 795 znaków w 836 ms MP3, każdy znak po 1 ms. Bez błędu, bez `notice`, strumień idzie dalej.
- Kontrola `text received: X/X` tego nie widzi, bo liczy znaki, nie dźwięk. Odcinek #3.9 audiobooka trafił na YouTube z dziurą 1:00:49: wypadły cztery akapity.
- Wykrycie jest pewne i tanie: porcja z co najmniej 20 literami i dźwiękiem krótszym niż 10 ms na literę. Na 25 792 porcjach ze wszystkich nagrań próg łapie 6 wadliwych (1,3–1,5 ms/literę) i nie daje żadnego fałszywego alarmu (najniższa zdrowa: 20 ms/literę, mediana 88).
- Błąd jest deterministyczny dla danego dokumentu: dwa niezależne nagrania `MS3_009` dały ciszę w tej samej porcji, co do milisekundy (3 649 410,6–3 650 246,5 ms). Nie da się go jednak odtworzyć samym tekstem porcji: ta sama porcja jako osobny dokument nagrała się w całości.
- Naprawa bez zmiany tekstu działa: nagrać samą porcję jako osobny dokument i wkleić jej MP3 w miejsce cichej porcji (po bajtach, na granicy ramek).
- AniShift (silnik `elevenreader` przy commicie `f595718`) jest na to podatny: odrzuca tylko kwestię o zerowej długości, a tu długość jest niezerowa (1 ms na znak).

## 1. Objaw

Fragment `MS3_009.align.jsonl`, porcja 69 (oba nagrania identyczne):

| Pole                      | Wartość                                                                                                         |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `offset_ms`               | 3 649 410,6                                                                                                     |
| znaki                     | 795 (od „Widziałam, jak to robisz nad jeziorem…” do „— Nie mam pojęcia — odparł Harry. `<break time="0.6s"/>`”) |
| `charStartTimesMs`        | 0, 1, 2, …, 834 (liniowo)                                                                                       |
| `charDurationsMs`         | 1 (wszystkie, kilka po 2)                                                                                       |
| dźwięk porcji (ramki MP3) | 835,9 ms                                                                                                        |
| oczekiwany dźwięk         | ok. 50 s (ta sama porcja nagrana osobno: 49,4 s mowy)                                                           |
| ramki obok                | normalne: porcja 68 kończy się „Ja coś o tym wiem.”, porcja 70 zaczyna „Ale przez resztę drogi…”                |
| log                       | nic: brak `notice`, brak `WS close`, brak odstępu między ramkami                                                |

Ten sam ślad wcześniej, w `SS_3201-3225_v2` (wtedy niezauważony): porcje 133–134 (1140 s) i 775–776 (6462 s), za każdym razem dwie sąsiednie porcje, 1,3–1,5 ms na literę.

## 2. Gdzie powstaje

Na serwerze. Dawny rejestrator ElevenDownloaderPro (`Recorder.write_chunk`) zapisywał bajty `audio` i `alignment` z ramki bez zmian. Deduplikacja i `trim_chunk` nie działały: w logu nie ma `skipped` ani `trimmed`. Długość porcji w pliku (835,9 ms) jest równa sumie ramek MP3 z samej ramki WebSocket, a więc serwer wysłał tyle dźwięku.

Ślad „1 ms na znak” wygląda na zastępczy alignment, który serwer wstawia, gdy synteza porcji nie dała mowy. Przyczyny po stronie serwera nie znamy.

## 3. Czy to cenzura

Nie da się tego rozstrzygnąć z zewnątrz. Za i przeciw:

- Za filtrem treści: wszystkie trzy przypadki zawierają w dialogu zapowiedź zabicia kogoś („sama cię zabiję”; „pomógł mi zabić Irian”; „walczyli na śmierć i życie… nago?” i „jak już go zabijesz”).
- Przeciw prostemu filtrowi:
  - 132 porcje ze słowami „zabić/zabije/zabijać” przeszły (3 wyciszone).
  - Dwie porcje dalej w tym samym rozdziale „Groziła, że wejdzie na boisko i cię zabije” przeszło.
  - Brutalna scena (wymordowanie rodziny) przeszła.
  - Ta sama porcja 793 znaków jako osobny dokument (test `T1`) nagrała się w całości.
  - Zdanie „jak już go zabijesz” w `SS_3201-3225` (v1, inne porcje) przeszło.

Wniosek roboczy: wynik zależy od porcji razem z kontekstem (tekst poprzedzający, granice porcji), a nie od samego zdania. Pasuje to do klasyfikatora oceniającego całą porcję z kontekstem albo do deterministycznej awarii modelu v4 dla konkretnego wejścia. Z naszej strony oba przypadki obsługuje się tak samo.

## 4. Czy da się to odtworzyć

| Test                                                                                            | Wynik                                                                                                             |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Pełny `AUDIOBOOK_PL/MS3_009.txt`, jedno nagranie naraz, 2 próby                                 | 2/2: cisza w porcji 69, ten sam offset                                                                            |
| Sama porcja 69 (`T1`, 793 zn.), osobny dokument                                                 | mowa 49,4 s, jedna porcja 793 zn.; przeszło                                                                       |
| Porcja 68 + 69 (`T4`)                                                                           | przeszło                                                                                                          |
| Porcja 69 z „uduszę” zamiast „zabiję” (`T2`)                                                    | przeszło                                                                                                          |
| Porcja 69 bez groźby (`T3`)                                                                     | przeszło                                                                                                          |
| Rozdział do końca porcji 69 (`P1`, 56 tys. zn.) i to samo z „uduszę” (`P2`), dwa nagrania naraz | oba przeszły, ale serwer pociął je na małe porcje (mediana 34 zn., maks. 77), więc porcja 69 w ogóle nie powstała |

Rozmiar porcji zależy od serwera, nie od nas. Przy jednym nagraniu naraz porcje rosną do ~870 znaków. Przy dwóch równoległych `P1`/`P2` zostały małe. Wszystkie znane przypadki są w trybie dużych porcji (`MS3_009`: 937 porcji na 122 tys. znaków; `SS_…_v2`: 2320; zdrowe `SS_…` v1: 8852 porcji).

Odtwarzalność:

- **Na żywo:** pewna tylko przez pełny dokument nagrywany w pojedynkę (`MS3_009`, ok. 2–3 min przy 64x). Tańszego wyzwalacza nie znaleźliśmy.
- **W testach:** nie potrzeba sieci. Fiksturą jest ramka z porcji 69 (alignment z `run2_MS3_009/MS3_009.align.jsonl`, linia 70, plus 836 ms MP3 wycięte z `MS3_009.mp3` po ramkach między offsetami z punktu 1). Test: rejestrator albo walidator ma odrzucić tę porcję.

## 5. Wykrywanie

Reguła na porcję (ramkę z `audio` i `alignment`):

```text
litery = liczba znaków \w w tekście porcji po usunięciu tagów <...>
dźwięk = czas ramek MP3 tej porcji
wadliwa, gdy litery >= 20 i dźwięk / litery < 10 ms
```

- Kalibracja: 25 792 porcje z ≥20 literami.
  - Wadliwe: 1,3–1,5 ms/literę.
  - Najniższe zdrowe: 20,3 i 21,1 (testy tagów `<phoneme>`), dalej 43,9.
  - Mediana: 88,2.
- Zapasowy sygnał: ≥90% `charDurationsMs` ≤ 2 ms. Na tych danych pokrywa się z regułą, ale łapie też porcje złożone z samych tagów `<break>`, więc sam nie wystarcza.
- Reguła nie działa dla porcji poniżej 20 liter (krótkie wykrzyknienia mają naturalnie mało dźwięku). Wszystkie znane przypadki mają 86–563 litery.

## 6. Naprawa nagrania

Sprawdzone na `MS3_009`:

1. Nagrać tekst cichej porcji jako osobny dokument. W teście przyszedł w jednej porcji z pełną mową.
2. Uciąć jego końcową ciszę (koniec dokumentu, ok. 2,2 s) do ~0,6 s za ostatnim znakiem z alignmentu.
3. W nagraniu głównym wyciąć bajty cichej porcji. Granice wyznacza cięcie po ramkach od początku pliku dla `offset_ms` porcji i następnej, a w ich miejsce wstawić bajty z kroku 2. Format jest ten sam (MP3 128 kb/s, mono, 44,1 kHz), więc bez ponownego kodowania.
4. Sprawdzić: długość = stara − 835,9 ms + nowa porcja; brak ciszy > 0,8 s w okolicy wklejki.

Nie tnij po czasie z dekodera (`ffmpeg atrim`). Pliki nagrane dawnym downloaderem ElevenDownloaderPro mają uszkodzone ramki („Header missing”), dekoder je pomija i czas się przesuwa: w teście o 4,4 s.

Ponowne nagranie całego dokumentu nie pomaga: wynik jest ten sam (2/2). Zmiana tekstu („uduszę”) pomaga tylko w osobnym dokumencie; w pełnym rozdziale tego nie sprawdziliśmy.

## 7. AniShift

`anishift/services/tts/engines/elevenreader/recorder.py` (commit `f595718`) ma tę samą logikę co dawny rejestrator ElevenDownloaderPro.

- `service.py` sprawdza:
  - sumę znaków (`recorder.chars` vs `char_count`);
  - zgodność tekstu kwestii;
  - od `f595718` także kwestię o zerowej długości, która dostaje pusty `PartTiming` i `TtsInputError` tylko dla siebie.
- Cicha porcja ma długość niezerową, więc przechodzi wszystkie trzy kontrole (wniosek z kodu, nie test na żywo):
  - każda kwestia w porcji dostaje klip o długości liczby jej znaków w ms (np. 200 znaków = 0,2 s);
  - odcinek kończy się sukcesem z kilkoma pustymi klipami w środku.
- Najwęższe miejsce na kontrolę to `part_spans`, obok sprawdzenia `ends[last] < starts[first]`:
  - kwestia z ≥20 literami i czasem < 10 ms na literę dostaje ten sam los co kwestia bez długości (pusty `PartTiming` i `TtsInputError` tylko dla niej);
  - ponowna próba tej kwestii poza dokumentem zadziała (punkt 6).
- Druga warstwa to reguła z punktu 5 w `StreamRecorder._write_chunk`. Zapisuje ostrzeżenie z indeksem porcji i liczbami, bez tekstu.

## 8. Otwarte pytania

- Co dokładnie wywołuje błąd (treść, kontekst, długość porcji)? Wymagałoby serii nagrań pełnego dokumentu z jedną zmianą naraz, po ok. 3 min każde.
- Czy serwer kiedyś sygnalizuje to polem `notice`? W znanych przypadkach było `null`.

## Stan w ElevenDownloaderPro

Reguła z punktu 5 (co najmniej 20 liter i mniej niż 10 ms dźwięku na literę) działa w dwóch miejscach:

- w rejestratorze silnika (`src/edp/engine/recorder.py`), który liczy dźwięk porcji z ramek MP3 (`mp3_frames.frames_duration_ms`) i oznacza porcję jako cichą; część tekstu, której dotyczy cicha porcja, wychodzi z silnika jako niewypowiedziana (`spoken == False`);
- w userscripcie `userscript/edp.user.js`, gdzie cicha porcja daje ostrzeżenie w panelu.

`reading.py` czyta ciche części ponownie: razem jako jeden mniejszy dokument, a części wciąż ciche osobno, najwyżej dwa ponowne odczyty na część. Wynik skleja po ramkach MP3, bez dekodowania, czyli tak jak ręczna naprawa z punktu 6. Część cicha po wszystkich próbach trafia do pola `silent` w `<nazwa>.json`, a `edp` kończy się kodem wyjścia 3.
