"""Prompt versioning — SHA-256 hashing and manifest generation for prompt templates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass
class PromptVersion:
    """Represents a versioned prompt template."""
    name: str
    path: str
    content: str
    sha256: str

    @classmethod
    def from_file(cls, path: Path) -> PromptVersion:
        """Create a PromptVersion from a file path."""
        content = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return cls(
            name=path.stem,
            path=str(path),
            content=content,
            sha256=sha,
        )


def get_manifest(prompt_dir: str | Path) -> dict[str, PromptVersion]:
    """Build a manifest of all prompt files in the given directory.

    Args:
        prompt_dir: Path to the prompts directory.

    Returns:
        Dictionary mapping prompt name → PromptVersion.
    """
    prompt_path = Path(prompt_dir)
    manifest: dict[str, PromptVersion] = {}

    if not prompt_path.exists():
        logger.warning("prompt_dir_not_found", path=str(prompt_path))
        return manifest

    for md_file in sorted(prompt_path.glob("*.md")):
        version = PromptVersion.from_file(md_file)
        manifest[version.name] = version
        logger.debug(
            "prompt_loaded",
            name=version.name,
            sha256=version.sha256[:12],
        )

    logger.info(
        "prompt_manifest_built",
        count=len(manifest),
        prompts=list(manifest.keys()),
    )

    return manifest


def verify_manifest(
    manifest: dict[str, PromptVersion],
    prompt_dir: str | Path,
) -> list[str]:
    """Verify that prompt files on disk match the manifest checksums.

    Args:
        manifest: Previously built manifest.
        prompt_dir: Path to the prompts directory.

    Returns:
        List of prompt names that have changed since the manifest was built.
    """
    changed: list[str] = []
    prompt_path = Path(prompt_dir)

    for name, version in manifest.items():
        file_path = prompt_path / f"{name}.md"
        if not file_path.exists():
            changed.append(name)
            continue
        current = PromptVersion.from_file(file_path)
        if current.sha256 != version.sha256:
            changed.append(name)
            logger.info(
                "prompt_changed",
                name=name,
                old_sha=version.sha256[:12],
                new_sha=current.sha256[:12],
            )

    return changed
