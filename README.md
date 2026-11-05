# ElevenDownloaderPro

Records ElevenReader speech (Eleven v4) to MP3, together with part timings, word timings (`.json`) and sentence
subtitles (`.srt`). Two ways to use it:

- **`edp` command** (Python): uploads a text file, records it in your own Chrome and cleans the account up afterwards.
  Also records a document that is already in your library.
- **Userscript** (Tampermonkey): does the same inside the browser tab.

Both record from the moment the audio stream opens. `edp download` refuses a document that the page resumes from the
middle (rewind it to the beginning in ElevenReader first), and the userscript warns about it in its panel.

## `edp` command

Requires [uv](https://docs.astral.sh/uv/) and Google Chrome.

```bash
uv tool install git+https://github.com/MattyMroz/ElevenDownloaderPro
edp login                                         # sign in once in a Chrome window
edp record chapter.txt --voice fronczewski        # writes chapter.mp3, chapter.json, chapter.srt
edp download https://elevenreader.io/reader/library/<read_id> --out book.mp3
```

- Every non-empty line of the text file is one part, and the whole file is read as one ElevenReader document into one
  MP3. Several files are recorded at once, two at a time.
- A part the server leaves silent is read again in a smaller document; a part that stays silent is listed under
  `silent` and the command exits with 3.
- Square brackets are read as text; `--tags` sends them as Eleven v4 audio tags.
- Every command prints one JSON value on stdout and logs on stderr. `edp --help` lists the exit codes.
- The Chrome profile and session live in `~/.edp` (`--home` or `EDP_HOME` change it).

## Userscript

1. Install the **Tampermonkey** extension. In Chrome, allow user scripts for it (Extensions → Tampermonkey → Details →
   "Allow User Scripts").
2. Open [`userscript/edp.user.js`](https://raw.githubusercontent.com/MattyMroz/ElevenDownloaderPro/main/userscript/edp.user.js)
   and confirm the installation. Tampermonkey updates it from the same address.
3. Open a document on [ElevenReader](https://elevenreader.io). The ElevenDownloaderPro panel records from the moment the stream opens
   and saves `.mp3`, `.json` and `.srt` when the document ends; "Save recording now" saves earlier.
4. To record your own text, paste it into the panel, pick a voice and press "Upload and record text". The document is
   deleted from your library afterwards and the account voice is restored.

The account reading speed must be 1x: at any other speed the server reads with the older v2 model. The panel offers
"Set account speed 1x" when it detects that.

## More

- [docs/research/elevenreader-protocol.md](docs/research/elevenreader-protocol.md): stream and HTTP API, measurements,
  costs and risks.
- [docs/research/elevenreader-tags.md](docs/research/elevenreader-tags.md): which markup tags work.
- [docs/research/silent-chunks.md](docs/research/silent-chunks.md): how silent parts are detected.

## Disclaimer

This tool is for **educational purposes only**. Please respect ElevenLabs' Terms of Service and usage limits. I am not
responsible for any banned accounts or misused data.
