"""Reject lines that carry a well-known API token shape.

Each pattern starts at a word boundary, so a word that merely ends in sk never
opens a key, and OpenAI-style and Hugging Face keys must hold a digit, so long
kebab-case CSS class names and camelCase identifiers pass. Lines are matched as bytes, so the file encoding does not
matter. The report names the token kind and line, never the value. Private
keys are left to detect-private-key. Paths come from argv.
"""

import re
import sys
from pathlib import Path
from typing import Final

TOKEN_KINDS: Final[dict[str, re.Pattern[bytes]]] = {
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "GitHub fine-grained token": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    "OpenAI-style API key": re.compile(rb"\bsk-(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{20,}"),
    "Stripe live key": re.compile(rb"\bsk_live_[A-Za-z0-9]{16,}"),
    "Google API key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}"),
    "Slack token": re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Netlify token": re.compile(rb"\bnfp_[A-Za-z0-9]{20,}"),
    "Hugging Face token": re.compile(rb"\bhf_(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{30,}\b"),
}
"""Token kind by the pattern that matches its shape."""


def main() -> int:
    """Report token-shaped values without echoing them; return 1 if there is one."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_bytes().splitlines(), start=1):
            for kind, pattern in TOKEN_KINDS.items():
                if pattern.search(line):
                    problems.append(f"{path}:{number}: {kind}")

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
