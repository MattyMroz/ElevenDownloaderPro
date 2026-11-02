# Znaczniki w tekście ElevenReadera: co działa

Test z 18 października 2026 r. ElevenReader w przeglądarce, polski tekst, prędkość czytania 1x (model Eleven v4).

## Wynik w skrócie

- Pewnie działają: zmiana wymowy (`<phoneme>`, IPA w ukośnikach), pauzy (`[pause]`, `[short pause]`, wielokropek, myślnik), ściszenie i szept, niższy głos (`[low]`), część odgłosów (śmiech, chrząknięcie, płacz, świszczący oddech) i część efektów dźwiękowych (grzmot, szczekanie psa, oklaski).
- Nie działają: wszystkie znaczniki SSML poza `<phoneme>` (`<break>`, `<prosody>`, `<emphasis>`, `<say-as>`, `<sub>`) oraz akcenty.
- Większość znaczników emocji lektor czyta na głos jako angielskie słowo, np. „Happy. Jutro rano…”. Czy przy okazji zmienia ton, nie da się stwierdzić bez odsłuchu.
- Wszystkie znaczniki, także te, które nic nie robią, liczą się do znaków rozliczanych w kredytach.

## Wyniki

Kolumna „Argon” i „Flash” pokazuje, czy dany sędzia wskazał nagranie ze znacznikiem w obu ocenach (zamiana kolejności A/B): „tak”, „nie”, „1/2” (tylko w jednej) albo „–” (brak oceny). Przy głośności, wysokości głosu i pauzach rozstrzyga pomiar, bo sędziowie tych cech nie słyszą (patrz „Sprawdzian sędziów”).

### Działa

| Znacznik                                                       | Co robi                                        | Dowód                                                                   |
| -------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------- |
| `<phoneme alphabet="ipa" ph="ˈʂafa">kot</phoneme>`             | zmienia wymowę słowa                           | Argon: tak, Flash: tak                                                  |
| `<phoneme alphabet="cmu-arpabet" ph="D AO1 M">kot</phoneme>`   | zmienia wymowę słowa                           | Argon: tak, Flash: tak                                                  |
| `/ˈʂafa/` (IPA w ukośnikach)                                   | czyta zapis IPA                                | Argon: tak, Flash: tak                                                  |
| `[pause]`, `[short pause]`                                     | pauza około 0,5 s                              | pomiar: 0,55 s i 0,51 s; bez znacznika 0,10 s                           |
| wielokropek `...`, myślnik `—`                                 | pauza około 0,5 s                              | pomiar: 0,51 s i 0,53 s                                                 |
| `[quietly]`, `[hushed]`, `[barely audible]`                    | wyraźnie ciszej                                | pomiar: −9,1 dB, −10,5 dB, −11,2 dB                                     |
| `[whispers]`                                                   | szept, ale czyta też słowo „whispers”          | pomiar: −10,6 dB; obaj sędziowie słyszą szept i słowo                   |
| `[whispering, fearful]`                                        | ciszej                                         | pomiar: −6,4 dB; Flash: tak                                             |
| `[softly]`                                                     | nieco ciszej                                   | pomiar: −3,8 dB, niewiele ponad zmienność nagrań (2,8 dB)               |
| `[low]`                                                        | niższy głos                                    | pomiar wysokości: ×0,69                                                 |
| `[laughs]`, `[clears throat]`, `[starts crying]`, `[wheezing]` | śmiech, chrząknięcie, płacz, świszczący oddech | Argon: tak, Flash: tak                                                  |
| `[thunder rumbling]`, `[dog barking]`, `[applause]`            | grzmot, szczekanie, oklaski                    | Argon: tak, Flash: tak                                                  |
| `[playful]`, `[disbelief]`                                     | zmiana tonu                                    | Argon: tak, Flash: tak                                                  |
| `[rushed]`, `[snappy]`                                         | szybciej, ale czyta też słowo                  | Argon: tak, Flash: tak; mowa krótsza o 0,2–0,3 s mimo dodatkowego słowa |

### Prawdopodobnie działa (ocenił tylko jeden sędzia)

| Znacznik                                               | Dowód                                                                      |
| ------------------------------------------------------ | -------------------------------------------------------------------------- |
| `[startled]`, `[mad]`, `[crying]`                      | Flash: tak; Argon nie dał ważnej odpowiedzi                                |
| `[gasps]`, `[clapping]`                                | Flash: tak, słyszy westchnienie i klaskanie przed zdaniem                  |
| `[speedy]` (czyta też słowo)                           | Flash: tak                                                                 |
| WIELKIE LITERY (`POCIĄGIEM`)                           | Flash: słowo wydłużone i podkreślone, po nim pauza; zdanie dłuższe o 1,1 s |
| `[bored]`, `[content]`, `[trusting]` (czyta też słowo) | Flash: tak                                                                 |

### Nie działa

| Znacznik                                                                                             | Dowód                                                                             |
| ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `<break time="1s"/>`, `<break time="3s"/>`                                                           | pomiar: pauza 0,10 s i 0,09 s, jak bez znacznika                                  |
| `<prosody rate="x-slow">`, `<prosody rate="x-fast">`                                                 | długość 4,16 s w obu przypadkach, bez znacznika 4,08 s                            |
| `<prosody volume="x-loud">`                                                                          | pomiar: −0,1 dB                                                                   |
| `<prosody pitch="x-high">`                                                                           | pomiar wysokości: ×1,05, w granicach zmienności                                   |
| `<emphasis>`, `<sub alias>`, `<say-as interpret-as="characters">`                                    | obaj sędziowie: brak różnicy; „kot” nie jest literowane, „ONZ” nie jest rozwijane |
| `[British accent]`, `[French accent]`, `[Irish accent]`, `[strong Russian accent]`, `[pirate voice]` | obaj sędziowie: nie                                                               |
| `[sings]`, `[laughs harder]`, `[powerful]`, `[aggressive]`, `[confused]`                             | obaj sędziowie: nie                                                               |
| `[long pause]`, `[slowly]`, `[drawn out]`                                                            | czyta słowo na głos, bez pauzy i bez zwolnienia                                   |
| `[vulnerable]`, `[despair]`                                                                          | czyta słowo na głos; obaj sędziowie: brak zmiany tonu                             |

### Czytane na głos, zmiana tonu niepewna

`[bitter]`, `[critical]`, `[repelled]`, `[anxious]`, `[stressed]`, `[scared]`, `[threatened]`, `[distant]`, `[peaceful]`, `[thoughtful]`, `[sad]`, `[happy]`, `[angry]`, `[busy]`, `[tired]`, `[let down]`, `[curious]`, `[sarcastic]`

Lektor mówi angielskie słowo przed zdaniem, więc zdanie trwa o 0,5–1,2 s dłużej. Argon zwykle nie słyszy zmiany tonu, a Flash często ją wskazuje. Słowo na początku zdradza sędziemu, które nagranie ma znacznik, więc w tej grupie test nie jest ślepy i różnicy zdań nie da się rozstrzygnąć bez odsłuchu.

### Niepewne, do odsłuchu

| Znacznik                                                            | Dlaczego niepewne                                                             |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `[excited]`, `[amazed]`, `[proud]`, `[optimistic]`, `[threatening]` | sędziowie odpowiadają różnie po zamianie kolejności A/B                       |
| `[sighs]` (czyta też słowo)                                         | Flash: tak, Argon: 1/2                                                        |
| `[shouts]` (czyta też słowo), `[booming]`                           | pomiar wysokości: ×1,9; podwojenie może być błędem pomiaru (pomylenie oktawy) |
| `[Australian accent]`                                               | Argon: tak, Flash: 1/2                                                        |
| `[footsteps]`, `[door creaking]`, `[gunshot]`                       | sędziowie odpowiadają różnie                                                  |

## Do odsłuchu

Każda para leży w `workspace/output/tag-test-clips/` jako `<znacznik>_z.mp3` (ze znacznikiem) i `<znacznik>_bez.mp3` (bez), np. `excited_z.mp3` i `excited_bez.mp3`. Najwięcej rozstrzygnie odsłuch grup „Niepewne” i „Czytane na głos, zmiana tonu niepewna”.

## Metoda

- Dwa dokumenty: 89 zdań ze znacznikami oraz 101 zdań bez żadnego znacznika. Znacznik może działać aż do następnego znacznika, więc zdania kontrolne są w osobnym dokumencie, a zdania bez nawiasów kwadratowych stoją przed pierwszym nawiasem.
- To samo zdanie w każdej parze: „Jutro rano pojadę pociągiem do miasta i wrócę późnym wieczorem.” Przy wymowie: „Na stole leży kot.” i „Komunikat wydała ONZ.”
- Każde zdanie wycięte jako osobny plik, cięcie w ciszy między akapitami. Tekst odebrany z serwera zgadza się z wysłanym akapit w akapit.
- Sędziowie: Gemini 4 Argon i Gemini 3.8 Flash, przez API, z nagraniami w treści zapytania. Każdy dostaje dwa nagrania A i B, nie wie, które ma znacznik, i ma wskazać, w którym słychać opisany efekt, podać transkrypcję obu i pewność. Każdą parę ocenia dwa razy, z zamienioną kolejnością A/B; liczy się wskazanie w obu ocenach z pewnością co najmniej 60.
- Pomiary każdego nagrania: długość mowy, głośność mowy, najdłuższa pauza w zdaniu, a przy kilku znacznikach wysokość głosu (autokorelacja). Zmiana liczy się dopiero poza zakresem zmienności nagrań kontrolnych: 3,99–4,67 s, −23,8 do −21,0 dB, pauza do 0,48 s, wysokość 121–136 Hz.

## Sprawdzian sędziów

| Próba                                                 | Poprawna odpowiedź | Argon              | Flash   |
| ----------------------------------------------------- | ------------------ | ------------------ | ------- |
| 6 par różnych nagrań tego samego zdania bez znacznika | brak różnicy       | 5/5 (1 brak oceny) | 6/6     |
| ten sam plik jako A i B, 2 razy                       | brak różnicy       | 1/1 (1 brak oceny) | 2/2     |
| nagranie ściszone o 12 dB                             | ciszej             | pomyłka            | pomyłka |
| nagranie spowolnione do 80%                           | wolniej            | trafił             | pomyłka |
| nagranie podwyższone o 25%                            | wyżej              | brak oceny         | pomyłka |

- Obaj sędziowie nie wymyślają różnic tam, gdzie ich nie ma.
- Żaden nie słyszy różnicy głośności ani wysokości głosu, dlatego te cechy rozstrzyga pomiar. Pomiar wysokości dał na nagraniu podwyższonym o 25% wynik ×1,23.
- Tempo słyszy tylko Argon. Flash przy `<break time="3s"/>` wskazał pauzę, której pomiar nie pokazuje.
- Argon przy 30 z 200 ocen zwrócił bełkot zamiast odpowiedzi; te oceny są oznaczone jako brak.

## Ograniczenia

- Każdy znacznik nagrany raz. Ten sam znacznik w innym zdaniu lub przy kolejnym czytaniu może zabrzmieć inaczej.
- Ustawienie ekspresyjności konta to `expressive`, najbardziej ekspresywne (pole `voice_expressiveness` w `user_config`, odczytane 17–18 października). W dniu testu nie odczytałem go ponownie.
- Emocji, akcentu i jakości efektów nie da się zmierzyć liczbami; tam rozstrzyga ucho, a sędziowie się różnią.
- Koszt testu: 17 038 znaków, około 1,7 kredytu.
