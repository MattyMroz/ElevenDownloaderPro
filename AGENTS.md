# ElevenDownloaderPro

Nagrywanie audio z ElevenReader i ElevenLabs do MP3: userscript Tampermonkey (`script.js`) i nagrywarka w Pythonie (`downloader.py`), która steruje prawdziwym Chrome przez CDP.

## Bramki jakości

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

`mypy` działa w trybie `strict` (`pyproject.toml`) i jest też hookiem `pre-push`.

## Mapa kodu

- `downloader.py`: jedyny moduł Pythona; uruchomienie `uv run downloader.py [PLIK.mp3] --url "<adres dokumentu>"`.
- `script.js`: userscript wklejany ręcznie do Tampermonkey, bez builda i bez `package.json`.
- `workspace/input/`, `workspace/output/`: katalogi robocze; git śledzi w nich tylko `.gitkeep`, nagrania `.mp3` i `.txt` lądują w `workspace/output/`.
- `.chrome-profile/`: profil Chrome z zalogowaną sesją ElevenReader, ignorowany przez git.

## Pułapki

- `downloader.py` wymaga Pythona 3.14 (`requires-python = ">=3.14"`) i używa jego składni `except KeyboardInterrupt, Error:` bez nawiasów; narzędzie na starszym Pythonie nie sparsuje pliku.
- `downloader.py` działa tylko na Windows: klawisze czyta przez `msvcrt`, a Chrome szuka w standardowych ścieżkach Windows (`--chrome` podaje inną).

## Git

- Commit: nagłówek Conventional Commits po angielsku, `type(scope): opis`, ze scope'em z listy w `.pre-commit-config.yaml`; po pustej linii streszczenie „co i dlaczego”; potem sekcja `Validation:` z kontrolami uruchomionymi na finalnym indeksie. Format: https://github.com/MattyMroz/agents/blob/main/presets/hooks/references/commit-message.md
- Kontrole uruchamiaj przez `mm-validate run "<kontrola>" -- <komenda>`, blok `Validation:` bierz z `mm-validate list`. Hooki `conventional-pre-commit` i `commit-validation` odrzucą inny commit.
- Pliki dodawaj po nazwie, nigdy `git add .`; bez `--no-verify`. Worktree'y tylko w `.worktrees/<nazwa>`.
