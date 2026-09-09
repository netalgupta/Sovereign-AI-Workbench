"""Tests for the shared strip_code_fences helper."""

from backend.utils.llm_output import strip_code_fences


def test_strips_json_labeled_fence():
    assert strip_code_fences('```json\n["a", "b"]\n```') == '["a", "b"]'


def test_strips_plain_fence():
    assert strip_code_fences('```\n{"x": 1}\n```') == '{"x": 1}'


def test_leaves_unfenced_text_unchanged_except_trimming():
    assert strip_code_fences('  ["a"]  ') == '["a"]'


def test_no_fence_no_change():
    assert strip_code_fences('not json at all') == 'not json at all'
