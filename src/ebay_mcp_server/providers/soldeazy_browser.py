"""浏览器内核探测：列出本机可用候选，按优先级尝试启动。

目标：**换任意一台机器都能起来**，不依赖硬编码路径，也不要求用户装 Chrome。

候选顺序：
1. 配置的 channel（默认 ``chrome``）
2. ``msedge`` —— Windows 10/11 自带，几乎一定存在
3. ``chromium`` —— Playwright 的标准通道（新无头模式）
4. Playwright 默认内核（无头时是 headless shell）
5. 扫描本机已下载的 Chromium / Chrome / Edge 可执行文件（不受版本号不匹配影响）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

CACHE_FILE = "browser_choice.json"


def _browser_roots() -> list[Path]:
    """Playwright 可能把浏览器放在这些位置。"""

    roots: list[Path] = []
    env_path = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env_path and env_path != "0":
        roots.append(Path(env_path))

    for base in (
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        str(Path.home() / "AppData" / "Local"),
        str(Path.home() / ".cache"),
        "/root/.cache",
    ):
        if not base:
            continue
        candidate = Path(base) / "ms-playwright"
        if candidate not in roots:
            roots.append(candidate)
    return roots


def installed_chromiums() -> list[Path]:
    """扫本机已下载的 Chromium 可执行文件，版本号大的优先。"""

    found: list[tuple[int, Path]] = []
    for root in _browser_roots():
        if not root.is_dir():
            continue
        for entry in root.glob("chromium-*"):
            if not entry.is_dir() or "headless" in entry.name:
                continue
            try:
                revision = int(entry.name.split("-")[1])
            except (IndexError, ValueError):
                revision = 0
            for relative in (
                "chrome-win64/chrome.exe",
                "chrome-win/chrome.exe",
                "chrome-linux/chrome",
                "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            ):
                candidate = entry / relative
                if candidate.is_file():
                    found.append((revision, candidate))
    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _revision, path in found]


def installed_browsers() -> list[tuple[str, Path]]:
    """列出手动安装的 Chrome / Edge 可执行文件（按常见安装位置）。"""

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")

    candidates = [
        ("Chrome", Path(program_files) / "Google/Chrome/Application/chrome.exe"),
        ("Chrome", Path(program_files_x86) / "Google/Chrome/Application/chrome.exe"),
        ("Edge", Path(program_files) / "Microsoft/Edge/Application/msedge.exe"),
        ("Edge", Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe"),
        ("Chrome", Path("/usr/bin/google-chrome")),
        ("Chromium", Path("/usr/bin/chromium")),
        ("Chromium", Path("/usr/bin/chromium-browser")),
    ]
    if local_appdata:
        candidates.append(
            ("Chrome", Path(local_appdata) / "Google/Chrome/Application/chrome.exe")
        )

    seen: set[Path] = set()
    result: list[tuple[str, Path]] = []
    for label, path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        result.append((label, path))
    return result


def build_plan(configured_channel: str) -> list[dict[str, Any]]:
    """构造候选计划：channel 优先，其次是能扫到的可执行文件。"""

    plan: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(channel: str, executable: Path | None, label: str) -> None:
        key = (channel, str(executable) if executable else "")
        if key in seen:
            return
        seen.add(key)
        plan.append(
            {
                "label": label,
                "channel": channel,
                "executable": str(executable) if executable else "",
            }
        )

    if configured_channel:
        add(configured_channel, None, configured_channel)

    # Windows 自带 Edge，最稳的兜底
    if sys.platform == "win32":
        add("msedge", None, "msedge")

    add("chromium", None, "chromium")
    add("", None, "Playwright 默认内核")

    for label, path in installed_browsers():
        add("", path, f"{label} {path.name} @ {path.parent.as_posix()}")
    for path in installed_chromiums():
        add("", path, f"已下载 Chromium {path.parent.parent.name}")

    return plan


def load_cache(directory: Path) -> dict[str, Any] | None:
    path = directory / CACHE_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError):
        return None


def save_cache(directory: Path, choice: dict[str, Any]) -> None:
    try:
        (directory / CACHE_FILE).write_text(
            json.dumps(choice, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def reorder(plan: Iterable[dict[str, Any]], cached: dict[str, Any] | None) -> list[dict[str, Any]]:
    """把上次成功的选择提到最前面，省去每次开机重复探测。"""

    items = list(plan)
    if not cached:
        return items
    key = (cached.get("channel", ""), cached.get("executable", ""))
    for index, item in enumerate(items):
        if (item["channel"], item["executable"]) == key:
            return [items[index]] + items[:index] + items[index + 1 :]
    return items
