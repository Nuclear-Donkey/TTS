"""Tests for macOS hotkey key resolution."""
from __future__ import annotations

from pynput.keyboard import Key, KeyCode

from voice_input_macos.hotkey import _resolve_ptt_key


def test_caps_lock():
    assert _resolve_ptt_key("caps_lock") == Key.caps_lock


def test_right_option():
    assert _resolve_ptt_key("right_option") == Key.alt_r


def test_left_option():
    assert _resolve_ptt_key("left_option") == Key.alt_l


def test_function_keys():
    assert _resolve_ptt_key("f9") == Key.f9
    assert _resolve_ptt_key("f12") == Key.f12


def test_single_char():
    result = _resolve_ptt_key("x")
    assert isinstance(result, KeyCode)


def test_unknown_falls_back_to_caps_lock():
    assert _resolve_ptt_key("nonexistent_key_xyz") == Key.caps_lock


def test_case_insensitive():
    assert _resolve_ptt_key("CAPS_LOCK") == Key.caps_lock
    assert _resolve_ptt_key("Right_Option") == Key.alt_r
