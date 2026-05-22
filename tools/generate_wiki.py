import argparse
import json
import os
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
DISMISSED_RE = re.compile(r"\b(dismess[oaie]?|obsolet[oaie]?|deprecated|deprecato|unused|non\s+usare|do\s*not\s*use)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CommandDoc:
    name: str
    program: str | None
    params: str | None
    mixed_staff: bool
    src_path: Path
    header_comment: str | None
    source: str
    is_old: bool = False


def read_list(path: Path) -> set[str]:
    if not path.exists():
        return set()
    items: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.add(line)
    return items


def extract_header_comment(text: str) -> str | None:
    lines = text.splitlines()
    buf: list[str] = []
    seen_nonempty = False
    for line in lines[:80]:
        stripped = line.strip()
        if not stripped:
            if seen_nonempty and buf:
                break
            continue
        seen_nonempty = True
        if stripped.startswith("//"):
            buf.append(stripped[2:].strip())
            continue
        if stripped.startswith("/*"):
            # Colleziona il blocco fino a */
            block: list[str] = []
            after = line.split("/*", 1)[1]
            if "*/" in after:
                block.append(after.split("*/", 1)[0])
                buf.extend([b.strip() for b in block if b.strip()])
                break
            block.append(after)
            for line2 in lines[lines.index(line) + 1 : lines.index(line) + 200]:
                if "*/" in line2:
                    block.append(line2.split("*/", 1)[0])
                    break
                block.append(line2)
            cleaned = []
            for b in block:
                b = b.strip()
                b = b.lstrip("*").strip()
                if b:
                    cleaned.append(b)
            if cleaned:
                buf.extend(cleaned)
            break
        if stripped.startswith("use ") or stripped.startswith("include "):
            # niente commento in testa
            break
        # altra roba: stop
        break
    if not buf:
        return None
    text_out = "\n".join(buf).strip()
    return text_out if text_out else None


def strip_author_date(comment: str) -> str:
    # Rimuove righe tipiche "autore + data/email" senza toccare note tecniche.
    out: list[str] = []
    for line in comment.splitlines():
        s = line.strip()
        if not s:
            continue
        if "@" in s:
            continue
        if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", s):
            continue
        if re.search(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b", s):
            continue
        if re.search(r"\b(updated|update|created|creato|modificato)\b", s, re.IGNORECASE):
            continue
        out.append(line)
    return "\n".join(out).strip()


def auto_description(name: str, program: str | None, raw: str) -> str:
    _ = (name, program, raw)
    return "Comando player: esegue un’azione lato script."


def scan_player_textcmd(poltest_root: Path) -> list[CommandDoc]:
    roots: list[tuple[str, Path]] = []

    core = poltest_root / "scripts" / "textcmd" / "player"
    if core.exists():
        roots.append(("core", core))

    pkg_root = poltest_root / "pkg"
    if pkg_root.exists():
        for src_path in sorted(pkg_root.rglob("textcmd/player/*.src")):
            roots.append((f"pkg:{src_path.parts[len(pkg_root.parts)]}", src_path.parent))
        # dedup: usiamo directory uniche
        seen_dirs: set[Path] = set()
        uniq: list[tuple[str, Path]] = []
        for source, dir_path in roots:
            if dir_path in seen_dirs:
                continue
            seen_dirs.add(dir_path)
            uniq.append((source, dir_path))
        roots = uniq

    if not roots:
        raise SystemExit("Nessuna cartella textcmd/player trovata (core o pkg).")

    docs: list[CommandDoc] = []
    for source, player_dir in roots:
        for src_path in sorted(player_dir.glob("*.src")):
            name = src_path.stem
            raw = src_path.read_text(encoding="utf-8", errors="replace")

            mixed_staff = any(marker in raw for marker in STAFF_MARKERS)

            program = None
            params = None
            for line in raw.splitlines():
                m = PROGRAM_RE.match(line)
                if m:
                    program = m.group(1)
                    params = m.group(2).strip() if m.group(2) is not None else None
                    break

            header_comment = extract_header_comment(raw)
            if header_comment:
                header_comment = strip_author_date(header_comment)
                if not header_comment:
                    header_comment = None
            dismissed = False
            if header_comment and DISMISSED_RE.search(header_comment):
                dismissed = True
            elif DISMISSED_RE.search(raw):
                dismissed = True

            docs.append(
                CommandDoc(
                    name=name,
                    program=program,
                    params=params,
                    mixed_staff=mixed_staff,
                    src_path=src_path,
                    header_comment=header_comment,
                    source=source,
                )
            )
    return docs


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def md_escape(text: str) -> str:
    return text.replace("\r", "").strip()


def render_command_page(doc: CommandDoc) -> str:
    shown_cmd = f".old {doc.name}" if doc.is_old else f".{doc.name}"
    title = f"`{shown_cmd}`"
    lines: list[str] = [f"# {title}", ""]
    lines.append("## Sintassi")
    lines.append("")
    lines.append(f"- Comando: `{shown_cmd}`")
    if doc.params:
        lines.append(f"- Parametri script: `{doc.params}`")
    if doc.program:
        lines.append(f"- Entry point: `{doc.program}`")
    lines.append(f"- Fonte: `{doc.source}`")
    if doc.is_old:
        lines.append("- Stato: `old`")
    lines.append("")

    lines.append("## Descrizione")
    lines.append("")
    # Descrizione automatica: evita di esporre codice o messaggi interni
    raw = doc.src_path.read_text(encoding="utf-8", errors="replace")
    lines.append(auto_description(doc.name, doc.program, raw))
    lines.append("")
    return "\n".join(lines)


def render_index(pages: list[CommandDoc]) -> str:
    lines: list[str] = [
        "# Comandi player",
        "",
        "Elenco generato automaticamente dai textcmd player di `poltest`.",
        "",
        "## Indice",
        "",
    ]
    current = [d for d in pages if not d.is_old]
    old = [d for d in pages if d.is_old]

    for doc in current:
        lines.append(f"- [{doc.name}](commands/{doc.name}.md)")
    if old:
        lines.append("")
        lines.append("## Old")
        lines.append("")
        for doc in old:
            lines.append(f"- [{doc.name}](old/{doc.name}.md)")
    lines.append("")
    return "\n".join(lines)


def load_previous_commands_json(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            out[name.lower()] = item
    return out


def render_changes_md(previous: dict[str, dict], current: list[dict]) -> str:
    current_map: dict[str, dict] = {}
    for item in current:
        name = item.get("name")
        if isinstance(name, str) and name:
            current_map[name.lower()] = item

    prev_keys = set(previous.keys())
    cur_keys = set(current_map.keys())

    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)

    modified: list[str] = []
    for key in sorted(prev_keys & cur_keys):
        prev_item = previous.get(key, {})
        cur_item = current_map.get(key, {})
        fields = ("program", "params", "notes_from_source", "source")
        if any(prev_item.get(f) != cur_item.get(f) for f in fields):
            modified.append(key)

    if not previous:
        return "\n".join(
            [
                "# Changes",
                "",
                "Prima generazione: non esiste uno storico precedente (`commands.json`).",
                "",
            ]
        )

    if not added and not removed and not modified:
        return "\n".join(
            [
                "# Changes",
                "",
                "Nessuna variazione rispetto alla generazione precedente.",
                "",
            ]
        )

    lines: list[str] = ["# Changes", ""]
    if added:
        lines.append("## Nuovi")
        lines.append("")
        for key in added:
            lines.append(f"- `.{current_map[key].get('name', key)}`")
        lines.append("")
    if removed:
        lines.append("## Rimossi")
        lines.append("")
        for key in removed:
            lines.append(f"- `.{previous[key].get('name', key)}`")
        lines.append("")
    if modified:
        lines.append("## Modificati")
        lines.append("")
        for key in modified:
            lines.append(f"- `.{current_map[key].get('name', key)}`")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poltest", required=True, help="Path root di poltest")
    ap.add_argument("--out", required=True, help="Cartella output docs (es. ./docs)")
    args = ap.parse_args()

    poltest_root = Path(args.poltest)
    out_root = Path(args.out)

    repo_root = Path(__file__).resolve().parents[1]
    exclude = read_list(repo_root / "config" / "exclude.txt")
    include_mixed = read_list(repo_root / "config" / "include_mixed.txt")

    scanned = scan_player_textcmd(poltest_root)

    exclude_l = {e.lower() for e in exclude}
    include_mixed_l = {i.lower() for i in include_mixed}

    filtered_map: dict[str, CommandDoc] = {}
    for doc in scanned:
        key = doc.name.lower()
        if TODO_NAME_RE.search(doc.name):
            continue
        if DISMISSED_RE.search(doc.name):
            continue
        raw = doc.src_path.read_text(encoding="utf-8", errors="replace")
        if DISMISSED_RE.search(raw) or (doc.header_comment and DISMISSED_RE.search(doc.header_comment)):
            continue
        if doc.mixed_staff and doc.name not in include_mixed and key not in include_mixed_l:
            continue
        # dedup per nome comando (case-insensitive): preferisci core
        is_old = doc.name in exclude or key in exclude_l
        doc2 = CommandDoc(
            name=doc.name,
            program=doc.program,
            params=doc.params,
            mixed_staff=doc.mixed_staff,
            src_path=doc.src_path,
            header_comment=doc.header_comment,
            source=doc.source,
            is_old=is_old,
        )

        if key in filtered_map:
            existing = filtered_map[key]
            if existing.source != "core" and doc.source == "core":
                filtered_map[key] = doc2
            continue
        filtered_map[key] = doc2

    filtered = sorted(filtered_map.values(), key=lambda d: d.name.lower())

    commands_json_path = out_root / "commands.json"
    previous = load_previous_commands_json(commands_json_path)

    # Scrivi pagine
    for doc in filtered:
        if doc.is_old:
            write_file(out_root / "old" / f"{doc.name}.md", render_command_page(doc))
        else:
            write_file(out_root / "commands" / f"{doc.name}.md", render_command_page(doc))

    # Rimuove pagine obsolete (comandi rimossi o esclusi)
    keep_commands = {f"{d.name}.md".lower() for d in filtered if not d.is_old}
    keep_old = {f"{d.name}.md".lower() for d in filtered if d.is_old}

    commands_dir = out_root / "commands"
    if commands_dir.exists():
        for md_path in commands_dir.glob("*.md"):
            if md_path.name.lower() not in keep_commands:
                md_path.unlink()

    old_dir = out_root / "old"
    if old_dir.exists():
        for md_path in old_dir.glob("*.md"):
            if md_path.name.lower() not in keep_old:
                md_path.unlink()

    write_file(out_root / "index.md", render_index(filtered))

    current_json = [
        {
            "command": f".old {d.name}" if d.is_old else f".{d.name}",
            "name": d.name,
            "program": d.program,
            "params": d.params,
            "source": d.source,
            "description": auto_description(
                d.name, d.program, d.src_path.read_text(encoding="utf-8", errors="replace")
            ),
            "status": "old" if d.is_old else "active",
        }
        for d in filtered
    ]
    write_file(
        commands_json_path,
        json.dumps(current_json, ensure_ascii=False, indent=2) + "\n",
    )
    write_file(out_root / "changes.md", render_changes_md(previous, current_json))

    print(f"Comandi trovati: {len(scanned)}")
    print(f"Comandi pubblicati: {len(filtered)}")
    if exclude:
        print(f"Esclusi via config/exclude.txt: {len(exclude)}")
    mixed_count = sum(1 for d in scanned if d.mixed_staff)
    print(f"Script con marker staff (totali): {mixed_count}")


if __name__ == "__main__":
    main()
