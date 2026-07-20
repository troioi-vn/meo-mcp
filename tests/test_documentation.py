import re
from pathlib import Path

from meo_mcp.oauth import ALLOWED_SCOPES

ROOT = Path(__file__).parents[1]
PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    *sorted(
        path
        for directory in (ROOT / "docs", ROOT / "todo", ROOT / ".agents" / "skills")
        for path in directory.rglob("*.md")
    ),
]


def test_relative_documentation_links_resolve() -> None:
    missing: list[str] = []
    link_pattern = re.compile(r"\]\(([^)]+)\)")

    for document in PUBLIC_DOCS:
        for raw_target in link_pattern.findall(document.read_text()):
            target = raw_target.strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (document.parent / target).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")

    assert missing == []


def test_tool_catalog_matches_the_implemented_scope_mapping() -> None:
    catalog = (ROOT / "docs" / "tools.md").read_text()

    assert ALLOWED_SCOPES == ["pets:read", "health:read", "pets:write", "health:write"]
    assert "`list_pets`" in catalog
    assert "`pets:read`" in catalog
    assert "`read`" in catalog
    assert "`GET /api/my-pets`" in catalog
    assert "`create_pet`" in catalog
    assert "`health:write`" in catalog
    assert "idempotency_key" in catalog
    assert "base_version" in catalog


def test_meo_mcp_skill_metadata_and_snapshot_match() -> None:
    skill_dir = ROOT / ".agents" / "skills" / "meo-mcp"
    skill = (skill_dir / "SKILL.md").read_text()
    reference = (skill_dir / "reference.md").read_text()
    interface = (skill_dir / "agents" / "openai.yaml").read_text()

    assert len(skill.splitlines()) < 500
    assert skill.startswith("---\nname: meo-mcp\ndescription:")
    for trigger in ("Meo MCP", "meo-mcp", "Streamable HTTP", "OAuth", "list_pets", "pets:read"):
        assert trigger in skill.split("---", 2)[1]
    for mapping in ("`list_pets`", "`pets:read`", "`health:read`", "`read`"):
        assert mapping in reference
    assert 'default_prompt: "Use $meo-mcp ' in interface


def test_public_documentation_has_no_private_inventory_markers() -> None:
    patterns = {
        "workstation path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"),
        "private IPv4 address": re.compile(
            r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
        ),
        "email identity": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "secret-store path": re.compile(r"\b(?:kv|secret|secrets)/[A-Za-z0-9._/-]+"),
    }
    leaks: list[str] = []

    for document in PUBLIC_DOCS:
        content = document.read_text()
        for label, pattern in patterns.items():
            if pattern.search(content):
                leaks.append(f"{document.relative_to(ROOT)}: {label}")

    assert leaks == []
