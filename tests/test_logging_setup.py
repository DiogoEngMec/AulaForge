"""Tests for aulaforge.logging_setup."""

from __future__ import annotations

import io

import pytest

from aulaforge.logging_setup import ensure_utf8_console


def test_ensure_utf8_console_does_not_raise_with_normal_streams() -> None:
    ensure_utf8_console()


def test_ensure_utf8_console_is_a_noop_for_streams_without_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_stdout = io.StringIO()  # no .reconfigure(), unlike sys.stdout
    monkeypatch.setattr("sys.stdout", fake_stdout)
    monkeypatch.setattr("sys.stderr", fake_stdout)

    ensure_utf8_console()  # must not raise
