#!/usr/bin/env python3
"""Update GitHub Actions references to their latest release tags."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAJOR_TAG_RE = re.compile(r"^v(?P<major>\d+)$")
SEMVER_TAG_RE = re.compile(
    r"^v(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$"
)
DATE_TAG_RE = re.compile(r"^(?P<year>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})$")
USES_RE = re.compile(
    r"(?P<prefix>\buses:\s*)(?P<repo>[\w.-]+/[\w.-]+)@(?P<ref>[^\s#]+)"
    r"(?P<suffix>[^\n#]*)(?P<comment>\s*#\s*(?P<tag>\S+).*)?$"
)
TAG_CACHE: dict[str, set[str]] = {}


def sort_key(match: re.Match[str]) -> tuple[int, ...]:
    return tuple(int(part) for part in match.groups())


def github_action_files() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / ".github").rglob("*")
        if path.suffix in {".yaml", ".yml"}
    )


def git_ls_remote(repo: str, *patterns: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable is required")  # noqa: TRY003

    result = subprocess.run(  # noqa: S603
        [git, "ls-remote", f"https://github.com/{repo}.git", *patterns],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def list_tags(repo: str) -> set[str]:
    if repo not in TAG_CACHE:
        TAG_CACHE[repo] = {
            ref.removeprefix("refs/tags/").removesuffix("^{}")
            for _, ref in (
                line.split(maxsplit=1)
                for line in git_ls_remote(repo, "refs/tags/*").splitlines()
            )
        }
    return TAG_CACHE[repo]


def latest_tag(repo: str, current_tag: str) -> str:
    current_match = (
        MAJOR_TAG_RE.fullmatch(current_tag)
        or SEMVER_TAG_RE.fullmatch(current_tag)
        or DATE_TAG_RE.fullmatch(current_tag)
    )
    if current_match is None:
        return current_tag

    pattern = current_match.re
    candidates = [
        (sort_key(match), tag)
        for tag in list_tags(repo)
        if (match := pattern.fullmatch(tag)) is not None
    ]
    return max(candidates)[1] if candidates else current_tag


def update_file(path: Path) -> bool:
    changed = False
    updated_lines: list[str] = []
    for line in path.read_text().splitlines(keepends=True):
        match = USES_RE.search(line.rstrip("\n"))
        if match is None:
            updated_lines.append(line)
            continue

        tag = latest_tag(match.group("repo"), match.group("ref"))
        replacement = (
            f"{match.group('prefix')}{match.group('repo')}@{tag}"
            f"{match.group('suffix')}"
            f"{match.group('comment') or ''}"
        )
        updated_line = USES_RE.sub(replacement, line.rstrip("\n"))
        updated_line += "\n" if line.endswith("\n") else ""
        changed = changed or updated_line != line
        updated_lines.append(updated_line)

    if changed:
        path.write_text("".join(updated_lines))
    return changed


def main() -> None:
    for path in github_action_files():
        if update_file(path):
            sys.stdout.write(f"{path.relative_to(REPO_ROOT)}\n")


if __name__ == "__main__":
    main()
