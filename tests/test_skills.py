import hashlib

import pytest

from ebay_mcp_server.errors import EbayMcpError
from ebay_mcp_server.skill_registry import SkillRegistry


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

