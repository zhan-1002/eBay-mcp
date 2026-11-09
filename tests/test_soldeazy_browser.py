"""浏览器候选探测的单元测试（不启动浏览器）。"""

from __future__ import annotations

from pathlib import Path

from ebay_mcp_server.providers import soldeazy_browser as probe


def test_plan_starts_with_configured_channel() -> None:
    plan = probe.build_plan("chrome")
    assert plan[0]["channel"] == "chrome"
    assert plan[0]["executable"] == ""


def test_plan_has_fallbacks_even_without_configured_channel() -> None:
    plan = probe.build_plan("")
    channels = [step["channel"] for step in plan]
    assert "chromium" in channels
    assert "" in channels
    assert all(step["label"] for step in plan)


def test_plan_has_no_duplicates() -> None:
    plan = probe.build_plan("chrome")
    keys = [(step["channel"], step["executable"]) for step in plan]
    assert len(keys) == len(set(keys))


def test_cache_roundtrip(tmp_path: Path) -> None:
    choice = {"label": "msedge", "channel": "msedge", "executable": ""}
    probe.save_cache(tmp_path, choice)
    assert probe.load_cache(tmp_path) == choice


def test_load_cache_returns_none_for_broken_file(tmp_path: Path) -> None:
    (tmp_path / probe.CACHE_FILE).write_text("{not json", encoding="utf-8")
    assert probe.load_cache(tmp_path) is None


def test_reorder_moves_cached_choice_first() -> None:
    plan = [
        {"label": "chrome", "channel": "chrome", "executable": ""},
        {"label": "msedge", "channel": "msedge", "executable": ""},
    ]
    moved = probe.reorder(plan, {"channel": "msedge", "executable": ""})
    assert moved[0]["channel"] == "msedge"
    assert [step["channel"] for step in moved[1:]] == ["chrome"]


def test_reorder_keeps_plan_when_cache_missing() -> None:
    plan = [{"label": "chrome", "channel": "chrome", "executable": ""}]
    assert probe.reorder(plan, None) == plan


def test_reorder_ignores_unknown_cached_choice() -> None:
    plan = [{"label": "chrome", "channel": "chrome", "executable": ""}]
    assert probe.reorder(plan, {"channel": "firefox", "executable": ""}) == plan


def test_installed_paths_are_files() -> None:
    for path in probe.installed_chromiums() + [p for _l, p in probe.installed_browsers()]:
        assert path.is_file()
