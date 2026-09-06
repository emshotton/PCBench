#!/usr/bin/env python3
"""Resolve the license of every board's source repository and record it in the board folder.

For each board under PCBs/, the source repository is inspected at the commit that was current
when the board was retrieved. The license GitHub detects there, or failing that any LICENSE,
LICENCE or COPYING file in the tree, is classified to an SPDX identifier. The board folder then
gets a normalised ``licenses`` entry in metadata.json, the verbatim license text as LICENSE, and
a NOTICE.md carrying attribution and the modification statement. Boards whose source has no
license are marked ``unlicensed`` and get a notice saying so instead of a LICENSE file.

Requires the GitHub CLI (``gh``) to be installed and authenticated.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

STATUS_LICENSED = "licensed"
STATUS_UNCLASSIFIED = "licensed-unclassified"
STATUS_UNLICENSED = "unlicensed"
STATUS_SOURCE_MISSING = "source-missing"

NAMES = {
    "MIT": "MIT License",
    "Apache-2.0": "Apache License 2.0",
    "BSD-2-Clause": 'BSD 2-Clause "Simplified" License',
    "BSD-3-Clause": 'BSD 3-Clause "New" or "Revised" License',
    "GPL-2.0": "GNU General Public License v2.0",
    "GPL-3.0": "GNU General Public License v3.0",
    "LGPL-2.0": "GNU Library General Public License v2.0",
    "LGPL-2.1": "GNU Lesser General Public License v2.1",
    "LGPL-3.0": "GNU Lesser General Public License v3.0",
    "AGPL-3.0": "GNU Affero General Public License v3.0",
    "MPL-2.0": "Mozilla Public License 2.0",
    "Unlicense": "The Unlicense",
    "WTFPL": "Do What The F*ck You Want To Public License",
    "CC0-1.0": "Creative Commons Zero v1.0 Universal",
    "CC-BY-3.0": "Creative Commons Attribution 3.0 Unported",
    "CC-BY-4.0": "Creative Commons Attribution 4.0 International",
    "CC-BY-SA-3.0": "Creative Commons Attribution Share Alike 3.0 Unported",
    "CC-BY-SA-4.0": "Creative Commons Attribution Share Alike 4.0 International",
    "CC-BY-NC-3.0": "Creative Commons Attribution Non Commercial 3.0 Unported",
    "CC-BY-NC-4.0": "Creative Commons Attribution Non Commercial 4.0 International",
    "CC-BY-NC-SA-3.0": "Creative Commons Attribution Non Commercial Share Alike 3.0 Unported",
    "CC-BY-NC-SA-4.0": "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
    "CERN-OHL-1.1": "CERN Open Hardware Licence v1.1",
    "CERN-OHL-1.2": "CERN Open Hardware Licence v1.2",
    "CERN-OHL-P-2.0": "CERN Open Hardware Licence Version 2 - Permissive",
    "CERN-OHL-W-2.0": "CERN Open Hardware Licence Version 2 - Weakly Reciprocal",
    "CERN-OHL-S-2.0": "CERN Open Hardware Licence Version 2 - Strongly Reciprocal",
    "TAPR-OHL-1.0": "TAPR Open Hardware License v1.0",
    "SHL-0.51": "Solderpad Hardware License v0.51",
    "SHL-2.0": "Solderpad Hardware License v2.0",
    "SHL-2.1": "Solderpad Hardware License v2.1",
}

HARDWARE_FAMILIES = ("CERN-OHL", "TAPR-OHL", "SHL", "CC-")


@dataclass(frozen=True)
class Pattern:
    family: str
    spdx_id: str
    title: re.Pattern | None
    mention: re.Pattern | None


def _p(family, spdx_id, title=None, mention=None, flags=re.IGNORECASE):
    return Pattern(
        family,
        spdx_id,
        re.compile(title, flags) if title else None,
        re.compile(mention, flags) if mention else None,
    )


PATTERNS = [
    _p("gnu", "AGPL-3.0", r"GNU AFFERO GENERAL PUBLIC LICENSE.{0,200}?Version 3\b", r"\bAGPL-?3", flags=0),
    _p("gnu", "LGPL-3.0", r"GNU LESSER GENERAL PUBLIC LICENSE.{0,200}?Version 3\b", r"\bLGPL-?3|GNU Lesser General Public License.{0,160}?version 3", flags=0),
    _p("gnu", "LGPL-2.1", r"GNU LESSER GENERAL PUBLIC LICENSE.{0,200}?Version 2\.1", r"\bLGPL-?2\.1|GNU Lesser General Public License.{0,160}?version 2\.1", flags=0),
    _p("gnu", "LGPL-2.0", r"GNU LIBRARY GENERAL PUBLIC LICENSE.{0,200}?Version 2\b", None, flags=0),
    _p("gnu", "GPL-3.0", r"GNU GENERAL PUBLIC LICENSE.{0,200}?Version 3\b", r"\bGPL-?(?:3|v3)\b|GNU General Public License.{0,160}?version 3\b", flags=0),
    _p("gnu", "GPL-2.0", r"GNU GENERAL PUBLIC LICENSE.{0,200}?Version 2\b", r"\bGPL-?(?:2|v2)\b|GNU General Public License.{0,160}?version 2\b", flags=0),
    _p("cern", "CERN-OHL-P-2.0", r"CERN Open Hardware Licen[cs]e Version 2\s*-\s*Permissive", r"CERN[- _]OHL[- _]P\b"),
    _p("cern", "CERN-OHL-W-2.0", r"CERN Open Hardware Licen[cs]e Version 2\s*-\s*Weakly Reciprocal", r"CERN[- _]OHL[- _]W\b"),
    _p("cern", "CERN-OHL-S-2.0", r"CERN Open Hardware Licen[cs]e Version 2\s*-\s*Strongly Reciprocal", r"CERN[- _]OHL[- _]S\b"),
    _p("cern", "CERN-OHL-1.2", r"CERN (?:Open Hardware Licen[cs]e|OHL) (?:v\.?|Version)\s*1\.2", r"CERN[- _]OHL[- _]1\.2"),
    _p("cern", "CERN-OHL-1.1", r"CERN (?:Open Hardware Licen[cs]e|OHL) (?:v\.?|Version)\s*1\.1", r"CERN[- _]OHL[- _]1\.1"),
    _p("tapr", "TAPR-OHL-1.0", r"TAPR Open Hardware License", r"TAPR[- ]OHL"),
    _p("shl", "SHL-2.1", r"Solderpad Hardware Licen[cs]e,? v(?:ersion)?\s*2\.1", r"SHL-2\.1"),
    _p("shl", "SHL-2.0", r"Solderpad Hardware Licen[cs]e,? v(?:ersion)?\s*2\.0", r"SHL-2\.0"),
    _p("shl", "SHL-0.51", r"Solderpad Hardware Licen[cs]e,? v(?:ersion)?\s*0\.51", r"SHL-0\.51"),
    _p("cc", "CC-BY-NC-SA-4.0", r"Attribution-NonCommercial-Share ?Alike 4\.0", r"CC[- ]BY-NC-SA[- ]4\.0"),
    _p("cc", "CC-BY-NC-SA-3.0", r"Attribution-NonCommercial-Share ?Alike 3\.0", r"CC[- ]BY-NC-SA[- ]3\.0"),
    _p("cc", "CC-BY-NC-4.0", r"Attribution-NonCommercial 4\.0", r"CC[- ]BY-NC[- ]4\.0"),
    _p("cc", "CC-BY-NC-3.0", r"Attribution-NonCommercial 3\.0", r"CC[- ]BY-NC[- ]3\.0"),
    _p("cc", "CC-BY-SA-4.0", r"Attribution[- ]Share[- ]?Alike 4\.0", r"CC[- ]BY-SA[- ]4\.0|Creative Commons Share-?alike 4\.0"),
    _p("cc", "CC-BY-SA-3.0", r"Attribution[- ]Share[- ]?Alike 3\.0", r"CC[- ]BY-SA[- ]3\.0"),
    _p("cc", "CC-BY-4.0", r"Attribution 4\.0 International", r"CC[- ]BY[- ]4\.0"),
    _p("cc", "CC-BY-3.0", r"Attribution 3\.0 Unported", r"CC[- ]BY[- ]3\.0"),
    _p("cc", "CC0-1.0", r"CC0 1\.0 Universal", r"\bCC0\b"),
    _p("mit", "MIT", r"Permission is hereby granted, free of charge", r"\bMIT licen[cs]e\b"),
    _p("apache", "Apache-2.0", r"Apache License,?\s+Version 2\.0", r"Apache[- ]2\.0|Apache License 2\.0"),
    _p("bsd", "BSD-3-Clause", None, r"BSD[- ]3-Clause"),
    _p("bsd", "BSD-2-Clause", None, r"BSD[- ]2-Clause"),
    _p("mpl", "MPL-2.0", r"Mozilla Public License,? (?:Version )?2\.0", r"\bMPL-?2\.0"),
    _p("unlicense", "Unlicense", r"free and unencumbered .{0,40}released into the public domain", None),
    _p("wtfpl", "WTFPL", r"DO WHAT THE F\w*CK YOU WANT TO PUBLIC LICENSE", r"\bWTFPL\b"),
]

BSD_TITLE = re.compile(r"Redistribution and use in source and binary forms", re.IGNORECASE)
BSD_THIRD_CLAUSE = re.compile(r"Neither the name", re.IGNORECASE)


def classify(text: str) -> list[str]:
    """SPDX ids whose license wording appears in ``text``, ordered by first appearance.

    A family (GNU, CERN, CC...) is matched on full license titles first; only when no title of
    that family is present do short mentions such as ``GPL-3.0`` count, because full texts
    routinely mention sibling licenses by name.
    """
    text = re.sub(r"\s+", " ", text)
    found: dict[str, int] = {}
    by_family: dict[str, list[Pattern]] = {}
    for pattern in PATTERNS:
        by_family.setdefault(pattern.family, []).append(pattern)
    for family, patterns in by_family.items():
        titles = [(p.spdx_id, m.start()) for p in patterns if p.title and (m := p.title.search(text))]
        if family == "bsd" and (m := BSD_TITLE.search(text)):
            titles = [("BSD-3-Clause" if BSD_THIRD_CLAUSE.search(text) else "BSD-2-Clause", m.start())]
        hits = titles or [(p.spdx_id, m.start()) for p in patterns if p.mention and (m := p.mention.search(text))]
        for spdx_id, pos in hits:
            found[spdx_id] = min(pos, found.get(spdx_id, pos))
    return sorted(found, key=found.get)


LEGACY_NAMES = {
    "MIT": "MIT",
    "MIT License": "MIT",
    "GNU General Public License v2.0": "GPL-2.0",
    "GNU General Public License v3.0": "GPL-3.0",
    "The Unlicense": "Unlicense",
    "Creative Commons Attribution Share Alike 4.0 International": "CC-BY-SA-4.0",
}


def spdx_from_legacy(legacy) -> str | None:
    """The SPDX id an old-shape ``licenses`` value already pins down, if any."""
    if isinstance(legacy, dict):
        spdx_id = legacy.get("spdx_id")
        return spdx_id if spdx_id and spdx_id != "NOASSERTION" else None
    if isinstance(legacy, list):
        ids = [LEGACY_NAMES[e["name"]] for e in legacy if isinstance(e, dict) and e.get("name") in LEGACY_NAMES]
        return ids[0] if len(ids) == 1 else None
    return None


def legacy_key(legacy) -> str | None:
    """The GitHub license key (``mit``, ``gpl-2.0``...) an old-shape value names, if any."""
    if isinstance(legacy, dict) and legacy.get("key"):
        return legacy["key"]
    spdx_id = spdx_from_legacy(legacy)
    return spdx_id.lower() if spdx_id else None


RAW_URL = re.compile(r"^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/(.+)$")


def legacy_paths(legacy) -> list[str]:
    """License file paths that old kitspace-style entries link to."""
    if not isinstance(legacy, list):
        return []
    return [m.group(1) for e in legacy if isinstance(e, dict) and (m := RAW_URL.match(e.get("link") or ""))]


def repo_slug(source: str) -> str | None:
    m = re.match(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", source or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def iso_utc(retrieved_at: str) -> str:
    """Some boards were stamped with the Unicode ratio character in place of colons."""
    return datetime.fromisoformat(retrieved_at.replace("\u2236", ":")).strftime("%Y-%m-%dT%H:%M:%SZ")


LICENSE_BASENAME = re.compile(r"^(licen[cs]e|copying)(\b|[._-]|$)", re.IGNORECASE)
BUNDLED_DIRS = {
    "lib", "libs", "library", "libraries", "third_party", "thirdparty", "third-party", "vendor",
    "vendors", "external", "deps", "dependencies", "node_modules", "3d", "3dmodels", "models",
    "packages", "footprints", "symbols", "fonts", "fp-lib", "sym-lib",
}


def license_file_candidates(paths: list[str]) -> list[str]:
    """License-like files in a tree listing, shallowest first, tree order within a depth.

    Files under bundled-library, footprint, symbol or 3D-model directories belong to what is
    vendored there, not to the board, so they are left out.
    """
    hits = []
    for i, p in enumerate(paths):
        parts = p.split("/")
        if not LICENSE_BASENAME.match(parts[-1]):
            continue
        if any(part.lower() in BUNDLED_DIRS for part in parts[:-1]):
            continue
        hits.append((len(parts) - 1, i, p))
    return [p for _, _, p in sorted(hits)]


@dataclass
class Resolution:
    spdx_id: str | None
    name: str | None
    path: str | None
    source_commit: str | None
    method: str | None
    status: str
    text: str | None
    detected_ids: list[str]

    @classmethod
    def unlicensed(cls, source_commit: str | None) -> "Resolution":
        return cls(None, None, None, source_commit, None, STATUS_UNLICENSED, None, [])

    @classmethod
    def missing(cls, spdx_id: str | None, text: str | None) -> "Resolution":
        name = NAMES.get(spdx_id) if spdx_id else None
        return cls(spdx_id, name, None, None, "legacy" if spdx_id else None, STATUS_SOURCE_MISSING, text, [spdx_id] if spdx_id else [])

    @classmethod
    def from_text(cls, text: str, path: str, source_commit: str | None, method: str) -> "Resolution":
        ids = classify(text)
        chosen = ids[0] if len(ids) == 1 else _hardware_choice(ids, text)
        status = STATUS_LICENSED if chosen else STATUS_UNCLASSIFIED
        return cls(chosen, NAMES.get(chosen) if chosen else None, path, source_commit, method, status, text, ids)


def _hardware_choice(ids: list[str], text: str) -> str | None:
    """In a combined notice that names one hardware license among software ones, the hardware
    license is the one covering the board files."""
    hardware = [i for i in ids if i.startswith(HARDWARE_FAMILIES)]
    if len(hardware) == 1 and re.search(r"\bhardware\b", text, re.IGNORECASE):
        return hardware[0]
    return None


def license_entry(res: Resolution) -> dict:
    return {
        "spdx_id": res.spdx_id,
        "name": res.name,
        "path": res.path,
        "source_commit": res.source_commit,
        "detected_by": res.method,
        "detected_ids": res.detected_ids,
        "status": res.status,
        "file": "LICENSE" if res.text else None,
    }


def notice_text(folder: str, meta: dict, res: Resolution) -> str:
    retrieved = meta.get("retrieved at", "")
    date = retrieved[:10]
    author = meta.get("author") or repo_slug(meta.get("source", "")) or "unknown"
    lines = [
        f"# {folder}",
        "",
        f"- Source: {meta.get('source', '')}",
        f"- Source commit: {res.source_commit or 'unknown'}",
        f"- Author: {author}",
        f"- Retrieved: {retrieved}",
    ]
    if res.status == STATUS_UNLICENSED:
        lines += [
            "- License: none",
            "",
            "No license was found in the source repository. The author retains all rights to",
            "these files. They are held in this dataset for research and evaluation only and are",
            "**not redistributable**; do not copy them elsewhere or publish results that include",
            "the board files themselves.",
        ]
    else:
        spdx = res.spdx_id or "not classified"
        where = f"`{res.path}` in the source repository" if res.path else "the source repository's metadata"
        lines += [f"- License: {spdx} ({res.name})" if res.name else f"- License: {spdx}"]
        if res.status == STATUS_SOURCE_MISSING:
            lines += ["- The source repository is no longer available on GitHub; the license shown is the one recorded when the board was retrieved."]
            if res.text:
                lines += [f"- License text: `LICENSE` in this directory holds the standard {spdx} text, since the source's own copy can no longer be fetched"]
            else:
                lines += ["- License text: not available"]
        elif res.text:
            lines += [f"- License text: `LICENSE` in this directory, copied verbatim from {where}"]
        else:
            lines += [f"- License text: not available; the license was recorded from {where}"]
        if res.status == STATUS_UNCLASSIFIED:
            ids = ", ".join(res.detected_ids) or "none"
            lines += [f"- The license file could not be reduced to a single SPDX identifier (wording found: {ids}); read `LICENSE` for the actual terms."]
    terms = (
        "carry the same restriction as the source: all rights reserved."
        if res.status == STATUS_UNLICENSED
        else "are provided under the same license as the source."
    )
    lines += [
        "",
        "## Modifications",
        "",
        "`raw.kicad_pcb` is the board as retrieved from the source. `processed.kicad_pcb` and",
        f"`final.json` are modified versions of it produced on {date} by the PCBench cleaning",
        "scripts under `Scripts/Data_cleaning` and `Scripts/Data_extraction`. The modified files",
        terms,
        "",
    ]
    return "\n".join(lines)


def write_board(folder: Path, meta: dict, res: Resolution) -> None:
    meta = {**meta, "licenses": license_entry(res)}
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    license_file = folder / "LICENSE"
    if res.text:
        license_file.write_text(res.text, encoding="utf-8")
    elif license_file.exists():
        license_file.unlink()
    (folder / "NOTICE.md").write_text(notice_text(folder.name, meta, res), encoding="utf-8")


def load_boards(pcbs: Path) -> list[tuple[str, dict]]:
    boards = []
    for meta_path in sorted(pcbs.glob("*/metadata.json")):
        boards.append((meta_path.parent.name, json.loads(meta_path.read_text(encoding="utf-8"))))
    return boards


def rebuild_master(pcbs: Path) -> None:
    boards = load_boards(pcbs)
    statuses = Counter(meta.get("licenses", {}).get("status") for _, meta in boards)
    repos = sorted({meta["source"] for _, meta in boards})
    master = {
        "Global Info": {
            "Num. Unique pcb designs": len(boards),
            "Num. Unique repos": len(repos),
            "Kicad source files": sum("kicad_pcb" in meta["raw"] for _, meta in boards),
            "Eagle source files": sum("kicad_pcb" not in meta["raw"] for _, meta in boards),
            "From Adafruit": sum(meta["org"] == "https://github.com/adafruit" for _, meta in boards),
            "From Sparkfun": sum(meta["org"] == "https://github.com/sparkfun" for _, meta in boards),
            "From Kitspace": sum("kitspace" in name for name, _ in boards),
            "Licensed": statuses[STATUS_LICENSED],
            "Licensed (unclassified)": statuses[STATUS_UNCLASSIFIED],
            "Unlicensed": statuses[STATUS_UNLICENSED],
            "Source missing": statuses[STATUS_SOURCE_MISSING],
            "Unique Repos": repos,
        }
    }
    master.update(boards)
    (pcbs / "master_metadata.json").write_text(json.dumps(master, indent=2) + "\n", encoding="utf-8")


def summary_text(boards: list[tuple[str, dict]]) -> str:
    entries = [(name, meta.get("licenses") or {}) for name, meta in boards]
    statuses = Counter(e.get("status") for _, e in entries)
    ids = Counter(e.get("spdx_id") for _, e in entries if e.get("spdx_id"))
    lines = [
        "# Board licenses",
        "",
        "Generated by `Scripts/Licensing/resolve_licenses.py`. Each board folder under `PCBs/`",
        "carries its own `LICENSE` and `NOTICE.md`; this file only summarises them.",
        "",
        "| Status | Boards |",
        "|---|---|",
        f"| Licensed | {statuses[STATUS_LICENSED]} |",
        f"| Licensed (unclassified) | {statuses[STATUS_UNCLASSIFIED]} |",
        f"| Source missing | {statuses[STATUS_SOURCE_MISSING]} |",
        f"| Unlicensed | {statuses[STATUS_UNLICENSED]} |",
        "",
        "| SPDX | Boards |",
        "|---|---|",
    ]
    lines += [f"| {spdx} | {count} |" for spdx, count in sorted(ids.items(), key=lambda kv: (-kv[1], kv[0]))]
    lines += ["", "## Unlicensed boards", "", "These boards' sources carry no license. They are not redistributable; see each board's `NOTICE.md`.", ""]
    lines += [f"- `{name}`" for name, e in entries if e.get("status") == STATUS_UNLICENSED]
    unclassified = [name for name, e in entries if e.get("status") == STATUS_UNCLASSIFIED]
    if unclassified:
        lines += ["", "## Boards with an unclassified license file", ""]
        lines += [f"- `{name}`" for name in unclassified]
    return "\n".join(lines) + "\n"


class GitHub:
    """GitHub REST calls through ``gh api``, cached on disk so reruns make no requests."""

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        self.calls = 0

    def api(self, endpoint: str):
        if endpoint in self.cache:
            return self.cache[endpoint]
        for attempt in range(4):
            proc = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
            self.calls += 1
            if proc.returncode == 0:
                result = {"ok": True, "data": json.loads(proc.stdout)}
                break
            if "rate limit" in proc.stderr.lower() or "abuse" in proc.stderr.lower():
                time.sleep(60 * (attempt + 1))
                continue
            result = {"ok": False, "error": proc.stderr.strip()[:200]}
            break
        else:
            raise RuntimeError(f"rate limited on {endpoint}")
        self.cache[endpoint] = result
        if self.calls % 25 == 0:
            self.save()
        return result

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache))

    def repo_exists(self, repo: str) -> bool:
        return self.api(f"repos/{repo}")["ok"]

    def commit_at(self, repo: str, when: str) -> str | None:
        for endpoint in (f"repos/{repo}/commits?until={when}&per_page=1", f"repos/{repo}/commits?per_page=1"):
            r = self.api(endpoint)
            if r["ok"] and r["data"]:
                return r["data"][0]["sha"]
        return None

    def license_at(self, repo: str, sha: str | None) -> dict | None:
        r = self.api(f"repos/{repo}/license" + (f"?ref={sha}" if sha else ""))
        return r["data"] if r["ok"] else None

    def tree_paths(self, repo: str, sha: str) -> list[str]:
        r = self.api(f"repos/{repo}/git/trees/{sha}?recursive=1")
        return [t["path"] for t in r["data"]["tree"] if t["type"] == "blob"] if r["ok"] else []

    def file_text(self, repo: str, path: str, sha: str | None) -> str | None:
        r = self.api(f"repos/{repo}/contents/{path}" + (f"?ref={sha}" if sha else ""))
        if not r["ok"] or r["data"].get("encoding") != "base64":
            return None
        return base64.b64decode(r["data"]["content"]).decode("utf-8", errors="replace")

    def generic_text(self, key: str) -> str | None:
        r = self.api(f"licenses/{key}")
        return r["data"].get("body") if r["ok"] else None


def resolve_repo(gh: GitHub, repo: str | None, retrieved_at: str, legacy) -> Resolution:
    if repo is None or not gh.repo_exists(repo):
        key = legacy_key(legacy)
        return Resolution.missing(spdx_from_legacy(legacy), gh.generic_text(key) if key else None)
    sha = gh.commit_at(repo, iso_utc(retrieved_at))
    detected = gh.license_at(repo, sha)
    text = base64.b64decode(detected["content"]).decode("utf-8", errors="replace") if detected else ""
    if text.strip():
        spdx_id = detected.get("license", {}).get("spdx_id")
        if spdx_id and spdx_id != "NOASSERTION":
            return Resolution(spdx_id, detected["license"].get("name") or NAMES.get(spdx_id), detected["path"], sha, "github", STATUS_LICENSED, text, [spdx_id])
        return Resolution.from_text(text, detected["path"], sha, "text-match")
    candidates = legacy_paths(legacy) + (license_file_candidates(gh.tree_paths(repo, sha)) if sha else [])
    fallback = None
    for path in dict.fromkeys(candidates):
        text = gh.file_text(repo, path, sha)
        if not text or not text.strip():
            continue
        res = Resolution.from_text(text, path, sha, "text-match")
        if res.status == STATUS_LICENSED:
            return res
        fallback = fallback or res
    return fallback or Resolution.unlicensed(sha)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--root", type=Path, default=root, help="repository root (default: this checkout)")
    parser.add_argument("--cache", type=Path, default=None, help="GitHub response cache (default: Scripts/Licensing/.cache/github.json)")
    parser.add_argument("--dry-run", action="store_true", help="resolve and report, but write nothing into PCBs/")
    parser.add_argument("--limit", type=int, default=None, help="only resolve the first N repositories")
    parser.add_argument("--repo", action="append", default=[], help="only resolve this owner/name (repeatable)")
    args = parser.parse_args(argv)

    pcbs = args.root / "PCBs"
    gh = GitHub(args.cache or args.root / "Scripts" / "Licensing" / ".cache" / "github.json")
    boards = load_boards(pcbs)
    by_repo: dict[str | None, list[tuple[str, dict]]] = {}
    for name, meta in boards:
        by_repo.setdefault(repo_slug(meta["source"]), []).append((name, meta))
    repos = [r for r in by_repo if not args.repo or r in args.repo][: args.limit]

    resolutions: dict[str, dict] = {}
    statuses: Counter = Counter()
    try:
        for i, repo in enumerate(repos, 1):
            members = by_repo[repo]
            earliest = min(meta["retrieved at"] for _, meta in members)
            res = resolve_repo(gh, repo, earliest, members[0][1].get("licenses"))
            statuses[res.status] += len(members)
            resolutions[repo or members[0][1]["source"]] = {**license_entry(res), "boards": [n for n, _ in members]}
            print(f"[{i}/{len(repos)}] {repo}: {res.status} {res.spdx_id or ''} ({len(members)} boards)", file=sys.stderr)
            if not args.dry_run:
                for name, meta in members:
                    write_board(pcbs / name, meta, res)
    finally:
        gh.save()

    print(json.dumps(dict(statuses), indent=2))
    if args.dry_run:
        return 0
    (args.root / "github_meta" / "license_resolution.json").write_text(json.dumps(resolutions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rebuild_master(pcbs)
    (args.root / "LICENSES.md").write_text(summary_text(load_boards(pcbs)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
