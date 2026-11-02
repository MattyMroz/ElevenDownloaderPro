from __future__ import annotations

import pytest
from fakes import ADAM_ID, FRONCZEWSKI_ID

from edp.engine import DEFAULT_VOICE_ALIAS, VOICES, resolve_voice
from edp.errors import ErrorCode, TtsVoiceError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [("fronczewski", FRONCZEWSKI_ID), ("ADAM", ADAM_ID), (f" {ADAM_ID} ", ADAM_ID), (FRONCZEWSKI_ID, FRONCZEWSKI_ID)],
)
def test_resolve_voice_alias_or_id_returns_offered_voice(value: str, expected: str) -> None:
    assert resolve_voice(value).voice_id == expected


def test_resolve_voice_unknown_raises_voice_error() -> None:
    with pytest.raises(TtsVoiceError) as error:
        resolve_voice("dallin")

    assert error.value.context.code is ErrorCode.TTS_VOICE_INVALID


def test_voices_offer_two_voices_with_fronczewski_default() -> None:
    assert tuple(VOICES) == ("fronczewski", "adam")
    assert DEFAULT_VOICE_ALIAS == "fronczewski"
    assert VOICES["fronczewski"].label == "Piotr Fronczewski"
