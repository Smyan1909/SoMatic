from __future__ import annotations

from somatic.skill import skill_summary, skill_text


def test_skill_text_loads_packaged_markdown():
    text = skill_text()
    assert "SoMatic" in text
    assert "vision init" in text or "vision_init" in text
    assert "click_near" in text or "click-near" in text
    assert "Operating Loop" in text


def test_skill_summary_is_short_and_mentions_workflow():
    summary = skill_summary()
    assert 50 < len(summary) < 800  # short enough for MCP instructions=
    assert "vision_init" in summary
    assert "screenshot_annotated" in summary
    assert "click_near" in summary
