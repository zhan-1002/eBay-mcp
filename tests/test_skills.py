import hashlib

import pytest

from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.skill_registry import SkillRegistry, _parse_frontmatter


def test_seven_packaged_skills_have_valid_manifests():
    registry = SkillRegistry()
    entries = registry.list()
    assert len(entries) == 7
    assert {entry.name for entry in entries} == {
        "ebay-api-diagnostics",
        "ebay-listing-retrieval",
        "ebay-sales-history",
        "ebay-seller-feedback",
        "ebay-taxonomy-navigation",
        "ebay-title-generation",
        "ebay-translation",
    }
    for entry in entries:
        assert entry.frontmatter["name"] == entry.name
        assert entry.frontmatter["description"]
        assert entry.uri == f"skill://{entry.name}/SKILL.md"
        assert entry.resources


def test_skill_resource_digest_matches_served_bytes():
    registry = SkillRegistry()
    entry = registry.get("ebay-title-generation")
    text, mime_type = registry.read(entry.uri)
    raw = text.encode("utf-8")
    skill_file = next(item for item in entry.resources if item.uri == entry.uri)
    assert skill_file.digest == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert skill_file.size == len(raw)
    assert mime_type == "text/markdown"
    assert "exactly 30" in text


@pytest.mark.parametrize(
    "uri",
    [
        "file://ebay-title-generation/SKILL.md",
        "skill://ebay-title-generation/../SKILL.md",
        "skill://unknown-skill/SKILL.md",
    ],
)
def test_skill_reads_fail_closed_for_invalid_or_unknown_uris(uri):
    with pytest.raises(EbayMcpError):
        SkillRegistry().read(uri)


# 回归：别的电脑 clone 下来是 CRLF（Git for Windows 默认 autocrlf=true），
# 旧实现要求文件以 "---\n" 开头，一遇到 CRLF 就抛 RuntimeError，
# 导致 ebay_mcp_server.server 直接 import 不了、MCP 服务根本起不来。
FRONTMATTER_LF = (
    "---\n"
    "name: demo-skill\n"
    "description: 演示用技能\n"
    "---\n"
    "\n"
    "# 正文\n"
    "内容\n"
)


def test_frontmatter_accepts_lf():
    values = _parse_frontmatter(FRONTMATTER_LF)
    assert values["name"] == "demo-skill"
    assert values["description"] == "演示用技能"


@pytest.mark.parametrize(
    "text",
    [
        FRONTMATTER_LF.replace("\n", "\r\n"),          # 纯 CRLF：Windows 全新 checkout
        "\ufeff" + FRONTMATTER_LF,                     # 带 BOM
        "\ufeff" + FRONTMATTER_LF.replace("\n", "\r\n"),
        FRONTMATTER_LF.replace("\n", "\r"),            # 老式 Mac 换行
    ],
    ids=["crlf", "bom", "bom+crlf", "cr"],
)
def test_frontmatter_accepts_windows_line_endings(text):
    values = _parse_frontmatter(text)
    assert values["name"] == "demo-skill"
    assert values["description"] == "演示用技能"


def test_frontmatter_still_rejects_missing_or_broken_blocks():
    with pytest.raises(RuntimeError):
        _parse_frontmatter("# 没有 frontmatter\n")
    with pytest.raises(RuntimeError):
        _parse_frontmatter("---\nname: demo\r\n")        # 没有结束标记
    with pytest.raises(RuntimeError):
        _parse_frontmatter("---\nname: demo\n---\n")     # 缺 description
    with pytest.raises(RuntimeError):
        _parse_frontmatter("---\n这不是 key-value\n---\n")

