"""M4: TerminalOutput."""

import pytest

from waken import Event, Response
from waken.plugins.outputs.terminal import TerminalOutput


async def test_terminal_output_prints_response_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = TerminalOutput()
    event = Event(source="terminal", target="echo", payload={})
    response = Response(text="Done.")

    await output.deliver(event, response)

    assert "Done." in capsys.readouterr().out


async def test_terminal_output_notes_files(capsys: pytest.CaptureFixture[str]) -> None:
    output = TerminalOutput()
    event = Event(source="terminal", target="echo", payload={})
    response = Response(text="Done.", files=["game.py"])

    await output.deliver(event, response)

    out = capsys.readouterr().out
    assert "Done." in out
    assert "game.py" in out


async def test_terminal_output_handles_no_text_or_files(
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = TerminalOutput()
    event = Event(source="terminal", target="echo", payload={})
    response = Response()

    await output.deliver(event, response)

    assert capsys.readouterr().out == ""
