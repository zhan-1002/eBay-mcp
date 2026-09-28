"""Packaged Agent Skill discovery and safe resource reads."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import files
import mimetypes
import re
from typing import Any
from urllib.parse import urlparse

from ebay_mcp_server.errors import EbayMcpError


_NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")


@dataclass(frozen=True)
class SkillFile:
    uri: str
    digest: str
    size: int
    mime_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "digest": self.digest,
            "size": self.size,
            "mimeType": self.mime_type,
        }


@dataclass(frozen=True)
class SkillEntry:
    name: str
    uri: str
    frontmatter: dict[str, Any]
    resources: tuple[SkillFile, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "frontmatter": dict(self.frontmatter),
            "resources": [item.as_dict() for item in self.resources],
        }


class SkillRegistry:
    def __init__(self):
        self._root = files("ebay_mcp_server").joinpath("skills")
        self._entries = self._discover()

    def list(self) -> list[SkillEntry]:
        return [self._entries[name] for name in sorted(self._entries)]

    def get(self, name_or_uri: str) -> SkillEntry:
        name = _skill_name(name_or_uri)
        try:
            return self._entries[name]
        except KeyError as exc:
            raise EbayMcpError(
                "SKILL_NOT_FOUND",
                f"Unknown skill: {name}",
                details={"available": sorted(self._entries)},
            ) from exc

    def read(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "skill" or not _NAME_RE.fullmatch(parsed.netloc):
            raise EbayMcpError("INVALID_SKILL_URI", f"Invalid skill URI: {uri}")
        name = parsed.netloc
        relative = parsed.path.lstrip("/")
        if not relative or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise EbayMcpError("INVALID_SKILL_URI", f"Invalid skill path: {uri}")
        entry = self.get(name)
        allowed = {item.uri: item for item in entry.resources}
        if uri not in allowed:
            raise EbayMcpError(
                "SKILL_RESOURCE_NOT_FOUND",
                f"Resource is not in the retained skill manifest: {uri}",
            )
        resource = self._root.joinpath(name)
        for part in relative.split("/"):
            resource = resource.joinpath(part)
        try:
            raw = resource.read_bytes()
        except OSError as exc:
            raise EbayMcpError(
                "SKILL_RESOURCE_NOT_FOUND",
                f"Skill resource could not be read: {uri}",
            ) from exc
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != allowed[uri].digest or len(raw) != allowed[uri].size:
            raise EbayMcpError(
                "SKILL_INTEGRITY_ERROR",
                f"Skill resource no longer matches its manifest: {uri}",
            )
        return raw.decode("utf-8"), allowed[uri].mime_type

    def _discover(self) -> dict[str, SkillEntry]:
        entries: dict[str, SkillEntry] = {}
        for directory in sorted(self._root.iterdir(), key=lambda value: value.name):
            if not directory.is_dir() or not _NAME_RE.fullmatch(directory.name):
                continue
            skill_file = directory.joinpath("SKILL.md")
            if not skill_file.is_file():
                continue
            raw = skill_file.read_bytes()
            frontmatter = _parse_frontmatter(raw.decode("utf-8"))
            name = str(frontmatter.get("name") or "")
            description = str(frontmatter.get("description") or "")
            if name != directory.name or not description:
                raise RuntimeError(
                    f"Invalid skill metadata for {directory.name}: "
                    "directory/name mismatch or empty description"
                )
            manifest: list[SkillFile] = []
            for relative, child in _walk_files(directory):
                child_raw = child.read_bytes()
                mime = mimetypes.guess_type(relative)[0] or "application/octet-stream"
                manifest.append(
                    SkillFile(
                        uri=f"skill://{name}/{relative}",
                        digest="sha256:" + hashlib.sha256(child_raw).hexdigest(),
                        size=len(child_raw),
                        mime_type=mime,
                    )
                )
            uri = f"skill://{name}/SKILL.md"
            entries[name] = SkillEntry(
                name=name,
                uri=uri,
                frontmatter=frontmatter,
                resources=tuple(manifest),
            )
        return entries


def _skill_name(name_or_uri: str) -> str:
    value = (name_or_uri or "").strip()
    if value.startswith("skill://"):
        value = urlparse(value).netloc
    if not _NAME_RE.fullmatch(value):
        raise EbayMcpError("INVALID_SKILL_NAME", f"Invalid skill name: {value}")
    return value


def _walk_files(directory, prefix: str = ""):
    for child in sorted(directory.iterdir(), key=lambda value: value.name):
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            yield from _walk_files(child, relative)
        elif child.is_file():
            yield relative.replace("\\", "/"), child


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        raise RuntimeError("SKILL.md must begin with YAML frontmatter")
    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise RuntimeError("SKILL.md frontmatter is not terminated")
    values: dict[str, Any] = {}
    for line in text[4:marker].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            raise RuntimeError(f"Invalid frontmatter line: {line}")
        value: Any = raw.strip().strip('"').strip("'")
        if value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        values[key.strip()] = value
    if not values.get("name") or not values.get("description"):
        raise RuntimeError("SKILL.md requires name and description")
    return values

