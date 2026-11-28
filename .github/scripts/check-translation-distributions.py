"""Check that both distributions contain the compiled gettext catalogs."""

# ruff: noqa: INP001

from pathlib import Path
from tarfile import open as open_tar
from zipfile import ZipFile

root = Path(__file__).resolve().parents[2]
source = root / "src" / "dj_craft_tally" / "locale"
catalogs = list(source.glob("*/LC_MESSAGES/django.mo"))
if not catalogs:
    message = "No compiled catalogs found"
    raise SystemExit(message)

(wheel,) = (root / "dist" / "translation-check").glob("*.whl")
(sdist,) = (root / "dist" / "translation-check").glob("*.tar.gz")
with ZipFile(wheel) as archive:
    for catalog in catalogs:
        member = f"dj_craft_tally/locale/{catalog.relative_to(source)}"
        if archive.read(member) != catalog.read_bytes():
            message = f"Incorrect wheel catalog: {member}"
            raise SystemExit(message)

with open_tar(sdist, "r:gz") as archive:
    for catalog in catalogs:
        suffix = f"/src/dj_craft_tally/locale/{catalog.relative_to(source)}"
        matches = [
            member for member in archive.getmembers() if member.name.endswith(suffix)
        ]
        if len(matches) != 1:
            message = f"Missing source distribution catalog: {suffix}"
            raise SystemExit(message)
        extracted = archive.extractfile(matches[0])
        if extracted is None or extracted.read() != catalog.read_bytes():
            message = f"Incorrect source distribution catalog: {suffix}"
            raise SystemExit(message)
