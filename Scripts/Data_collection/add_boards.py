#!/usr/bin/env python3
"""Add boards from GitHub repositories to PCBs/.

Reads a tab-separated list of ``owner/repo<TAB>path/to/board.kicad_pcb`` and, for each entry,
fetches the board at the repository's current default-branch commit and writes a new board
folder holding ``raw.kicad_pcb`` (the file as fetched), ``processed.kicad_pcb`` (the same board
with zone fills removed, routing kept), ``raw.kicad_pro`` when the source keeps a KiCad 6+
project file next to the board (its net classes are the board's design rules), and
``metadata.json`` in the dataset's shape. Boards with no nets, no routing or no board outline
are skipped and reported.

``final.json`` and ``visual.png`` are not produced: the PCB-RDL extractor under
``Scripts/Data_extraction`` handles the KiCad 5 file format only. Run
``Scripts/Licensing/resolve_licenses.py --repo owner/repo`` afterwards for each repository so
the new folders get their LICENSE, NOTICE.md and ``licenses`` entry.

Requires the GitHub CLI (``gh``) to be installed and authenticated.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

FORMAT_RELEASES = [
    (20260101, "10"),
    (20241201, "9"),
    (20240101, "8"),
    (20220901, "7"),
    (20210101, "6"),
    (20170101, "5"),
]


def parse_list(path: Path) -> list[tuple[str, str]]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        repo, board_path = line.split("\t", 1)
        entries.append((repo.strip(), board_path.strip()))
    return entries


def folder_name(repo: str, board_path: str, parents: int = 0) -> str:
    """``<repo>_<board stem>``, with the board's last ``parents`` directories in between when
    boards of one repository share a file name (``Rectifier/Main.kicad_pcb`` next to
    ``Rectifier SMD/Main.kicad_pcb``)."""
    parts = board_path.split("/")
    stem = parts[-1].removesuffix(".kicad_pcb")
    middle = "".join(f"{d}_" for d in parts[max(0, len(parts) - 1 - parents):-1])
    name = f"{repo.split('/', 1)[1]}_{middle}{stem}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def unique_folder_name(pcbs: Path, repo: str, board_path: str, taken: set[str]) -> str:
    """A folder name not already used in this run, and not already holding a different board."""
    for parents in range(board_path.count("/") + 1):
        name = folder_name(repo, board_path, parents)
        meta_path = pcbs / name / "metadata.json"
        if name in taken:
            continue
        if meta_path.exists():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if existing.get("source") != f"https://github.com/{repo}" or existing.get("source_path", board_path) != board_path:
                continue
        return name
    raise ValueError(f"no free folder name for {repo} {board_path}")


NET_REF = re.compile(r'\(net\s+(?:\d+\s+)?(?:"([^"]*)"|([^\s()"]+))\)')


def board_facts(text: str) -> dict:
    version = re.search(r"\(version\s+(\d+)\)", text)
    generator = re.search(r'\(generator_version\s+"([^"]+)"\)', text)
    layers_start = re.search(r"\(layers\s", text)
    layers_block = text[layers_start.start():_balanced_end(text, layers_start.start()) + 1] if layers_start else ""
    copper = len(re.findall(r'\(\d+\s+"?[A-Za-z0-9_]+\.Cu"?\s', layers_block))
    nets = {quoted or bare for quoted, bare in NET_REF.findall(text) if not bare.isdigit()} - {""}
    segments = len(re.findall(r"^\s*\((?:segment|arc)\s", text, re.MULTILINE))
    has_outline = bool(re.search(r'\(layer\s+"?Edge\.Cuts"?\)', text))
    return {
        "format_version": int(version.group(1)) if version else None,
        "generator_version": generator.group(1) if generator else None,
        "copper_layers": copper,
        "nets": len(nets),
        "segments": segments,
        "has_outline": has_outline,
    }


def kicad_release(facts: dict) -> str:
    if facts.get("generator_version"):
        return facts["generator_version"]
    version = facts.get("format_version") or 0
    for threshold, release in FORMAT_RELEASES:
        if version >= threshold:
            return release
    return str(version)


def rejection(facts: dict) -> str | None:
    if facts["nets"] < 2:
        return f"only {facts['nets']} net(s)"
    if facts["segments"] == 0:
        return "not routed"
    if not facts["has_outline"]:
        return "no board outline on Edge.Cuts"
    return None


def _balanced_end(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"unbalanced parentheses from offset {start}")


def unfill_zones(text: str) -> str:
    """The board text with every ``(filled_polygon ...)`` block removed; zone outlines and all
    routing stay, so pours regenerate on load."""
    out = []
    i = 0
    for m in re.finditer(r"\(filled_polygon\b", text):
        if m.start() < i:
            continue
        end = _balanced_end(text, m.start())
        chunk = text[i:m.start()]
        out.append(chunk.rstrip(" \t") if chunk.endswith(("\n", " ", "\t")) and text[end + 1:end + 2] == "\n" else chunk)
        i = end + 1
        if text[i:i + 1] == "\n" and out and out[-1].endswith("\n"):
            i += 1
    out.append(text[i:])
    return "".join(out)


def metadata(name: str, repo: str, board_path: str, commit: str, facts: dict, retrieved_at: str) -> dict:
    owner = repo.split("/", 1)[0]
    return {
        "org": f"https://github.com/{owner}",
        "source": f"https://github.com/{repo}",
        "author": owner,
        "retrieved at": retrieved_at,
        "raw": f"../../PCBs/{name}/raw.kicad_pcb",
        "cleaned": f"../../PCBs/{name}/processed.kicad_pcb",
        "json": "",
        "supplementary files": "",
        "licenses": None,
        "layers": facts["copper_layers"],
        "CAD version": f"KiCad {facts['format_version']}",
        "kicad_version": kicad_release(facts),
        "source_path": board_path,
        "source_commit": commit,
    }


def write_board(pcbs: Path, repo: str, board_path: str, commit: str, text: str, retrieved_at: str,
                project: str | None = None, name: str | None = None) -> str:
    name = name or folder_name(repo, board_path)
    folder = pcbs / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "raw.kicad_pcb").write_text(text, encoding="utf-8")
    (folder / "processed.kicad_pcb").write_text(unfill_zones(text), encoding="utf-8")
    if project:
        (folder / "raw.kicad_pro").write_text(project, encoding="utf-8")
    meta = metadata(name, repo, board_path, commit, board_facts(text), retrieved_at)
    if project:
        meta["supplementary files"] = f"../../PCBs/{name}/raw.kicad_pro"
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return name


def head_commit(repo: str) -> str:
    return subprocess.run(["gh", "api", f"repos/{repo}/commits/HEAD", "--jq", ".sha"], capture_output=True, text=True, check=True).stdout.strip()


def fetch(repo: str, commit: str, board_path: str) -> str:
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{quote(board_path)}"
    proc = subprocess.run(["curl", "-fsSL", "--max-time", "120", url], capture_output=True, check=True)
    return proc.stdout.decode("utf-8", errors="replace")


def fetch_project(repo: str, commit: str, board_path: str) -> str | None:
    """The ``.kicad_pro`` with the board's own stem, if the source has one."""
    try:
        return fetch(repo, commit, board_path.removesuffix(".kicad_pcb") + ".kicad_pro")
    except subprocess.CalledProcessError:
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("list", type=Path, help="tab-separated owner/repo and board path per line")
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--force", action="store_true", help="overwrite a board folder that already exists")
    args = parser.parse_args(argv)

    pcbs = args.root / "PCBs"
    commits: dict[str, str] = {}
    added, skipped = [], []
    taken: set[str] = set()
    for repo, board_path in parse_list(args.list):
        name = unique_folder_name(pcbs, repo, board_path, taken)
        taken.add(name)
        if (pcbs / name).exists() and not args.force:
            skipped.append((name, "already present"))
            continue
        commit = commits.setdefault(repo, head_commit(repo))
        text = fetch(repo, commit, board_path)
        why = rejection(board_facts(text))
        if why:
            skipped.append((name, why))
            continue
        retrieved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        project = fetch_project(repo, commit, board_path) if board_facts(text)["format_version"] > 20200000 else None
        write_board(pcbs, repo, board_path, commit, text, retrieved_at, project, name)
        added.append(name)
        print(f"added {name}" + (" (with project file)" if project else ""), file=sys.stderr)
    for name, why in skipped:
        print(f"skipped {name}: {why}", file=sys.stderr)
    print(json.dumps({"added": len(added), "skipped": len(skipped), "repositories": sorted(commits)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
