import argparse
import re
from dataclasses import dataclass
from pathlib import Path


PROGRAM_RE = re.compile(r"^\s*program\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)", re.IGNORECASE)

STAFF_MARKERS = (
    "CMDLEVEL_",
    "IsStaff(",
    ".cmdlevel",
)

TODO_NAME_RE = re.compile(r"\b(to[- ]?do|todo)\b", re.IGNORECASE)
DISMISSED_RE = re.compile(
    r"\b(dismess[oaie]?|obsolet[oaie]?|deprecated|deprecato|unused|non\s+usare|do\s*not\s*use)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScanItem:
    name: str
    src_path: Path
    source: str
    mixed_staff: bool


def read_list(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.add(s)
    return out


def strip_escript_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    return text


def scan_textcmd_player(poltest_root: Path) -> list[ScanItem]:
    roots: list[tuple[str, Path]] = []

    core = poltest_root / "scripts" / "textcmd" / "player"
    if core.exists():
        roots.append(("core", core))

    pkg_root = poltest_root / "pkg"
    if pkg_root.exists():
        for src_path in sorted(pkg_root.rglob("textcmd/player/*.src")):
            pkg_name = src_path.parts[len(pkg_root.parts)]
            roots.append((f"pkg:{pkg_name}", src_path.parent))

        seen_dirs: set[Path] = set()
        uniq: list[tuple[str, Path]] = []
        for source, dir_path in roots:
            if dir_path in seen_dirs:
                continue
            seen_dirs.add(dir_path)
            uniq.append((source, dir_path))
        roots = uniq

    items: list[ScanItem] = []
    for source, player_dir in roots:
        for src_path in sorted(player_dir.glob("*.src")):
            raw = src_path.read_text(encoding="utf-8", errors="replace")
            raw_nc = strip_escript_comments(raw)
            mixed_staff = any(m in raw_nc for m in STAFF_MARKERS)
            items.append(ScanItem(name=src_path.stem, src_path=src_path, source=source, mixed_staff=mixed_staff))
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poltest", required=True)
    ap.add_argument("--repo", required=True, help="Path repo wiki (per leggere config)")
    args = ap.parse_args()

    poltest_root = Path(args.poltest)
    repo_root = Path(args.repo)

    exclude = read_list(repo_root / "config" / "exclude.txt")
    include_mixed = read_list(repo_root / "config" / "include_mixed.txt")
    exclude_l = {e.lower() for e in exclude}
    include_mixed_l = {i.lower() for i in include_mixed}

    scanned = scan_textcmd_player(poltest_root)

    # dedup per nome (case-insensitive): preferisci core
    by_name: dict[str, ScanItem] = {}
    for it in scanned:
        k = it.name.lower()
        if k in by_name:
            if by_name[k].source != "core" and it.source == "core":
                by_name[k] = it
        else:
            by_name[k] = it

    filtered: list[tuple[str, str]] = []  # (name, reason)
    for k, it in sorted(by_name.items()):
        raw = it.src_path.read_text(encoding="utf-8", errors="replace")

        if TODO_NAME_RE.search(it.name):
            filtered.append((it.name, "todo-name"))
            continue
        if DISMISSED_RE.search(it.name) or DISMISSED_RE.search(raw):
            filtered.append((it.name, "dismissed/obsolete"))
            continue
        if it.name in exclude or it.name.lower() in exclude_l:
            filtered.append((it.name, "exclude.txt"))
            continue
        if it.mixed_staff and it.name not in include_mixed and it.name.lower() not in include_mixed_l:
            filtered.append((it.name, "mixed-staff (filtered)"))
            continue

    # Stampa elenco per reason
    by_reason: dict[str, list[str]] = {}
    for name, reason in filtered:
        by_reason.setdefault(reason, []).append(name)

    for reason in sorted(by_reason.keys()):
        print(f"[{reason}] ({len(by_reason[reason])})")
        for name in sorted(by_reason[reason], key=str.lower):
            print(f"  - .{name}")
        print()

    total_scanned = len(by_name)
    total_filtered = len(filtered)
    total_published = total_scanned - total_filtered
    print(f"TOTAL scanned: {total_scanned}")
    print(f"TOTAL filtered: {total_filtered}")
    print(f"TOTAL published: {total_published}")


if __name__ == "__main__":
    main()

