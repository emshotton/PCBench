import json
from pathlib import Path

import pytest

import resolve_licenses as rl


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Permission is hereby granted, free of charge, to any person obtaining a copy", ["MIT"]),
        ("Apache License\nVersion 2.0, January 2004", ["Apache-2.0"]),
        ("Redistribution and use in source and binary forms ... Neither the name of the copyright holder", ["BSD-3-Clause"]),
        ("Redistribution and use in source and binary forms, with or without modification", ["BSD-2-Clause"]),
        ("GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007", ["GPL-3.0"]),
        ("GNU GENERAL PUBLIC LICENSE\n====\nCopyright (c) 2015 Someone\nVersion 3, 29 June 2007", ["GPL-3.0"]),
        ("you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 3 of the License", ["GPL-3.0"]),
        ("under the terms of the GNU General Public License as published by the Free Software Foundation, version 2", ["GPL-2.0"]),
        ("under the terms of the GNU Lesser General Public License as published by the Free Software Foundation; either version 2.1 of the License", ["LGPL-2.1"]),
        ("CERN Open Hardware License Version 1.2, or later.", ["CERN-OHL-1.2"]),
        ("licensed under the Solderpad Hardware License, Version 0.51", ["SHL-0.51"]),
        ("GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991", ["GPL-2.0"]),
        ("GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007", ["LGPL-3.0"]),
        ("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007", ["AGPL-3.0"]),
        ("Attribution-ShareAlike 4.0 International", ["CC-BY-SA-4.0"]),
        ("Attribution-ShareAlike 3.0 Unported", ["CC-BY-SA-3.0"]),
        ("Attribution 4.0 International", ["CC-BY-4.0"]),
        ("Attribution-NonCommercial-ShareAlike 4.0 International", ["CC-BY-NC-SA-4.0"]),
        ("Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License", ["CC-BY-NC-SA-3.0"]),
        ("Creative Commons Attribution-NonCommercial 3.0 Unported", ["CC-BY-NC-3.0"]),
        ("hardware is released under Creative Commons Share-alike 4.0 International", ["CC-BY-SA-4.0"]),
        ("CC0 1.0 Universal", ["CC0-1.0"]),
        ("CERN Open Hardware Licence Version 2 - Permissive", ["CERN-OHL-P-2.0"]),
        ("CERN Open Hardware Licence Version 2 - Weakly Reciprocal", ["CERN-OHL-W-2.0"]),
        ("CERN Open Hardware Licence Version 2 - Strongly Reciprocal", ["CERN-OHL-S-2.0"]),
        ("designs located at ./hardware are available under the CERN-OHL-P v2 license", ["CERN-OHL-P-2.0"]),
        ("CERN OHL v.1.2", ["CERN-OHL-1.2"]),
        ("CERN Open Hardware Licence v1.1", ["CERN-OHL-1.1"]),
        ("The TAPR Open Hardware License\nVersion 1.0 (May 25, 2007)", ["TAPR-OHL-1.0"]),
        ("This is free and unencumbered software released into the public domain.", ["Unlicense"]),
        ("This is free and unencumbered software and hardware design released into the public domain.", ["Unlicense"]),
        ("DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE", ["WTFPL"]),
        ("Mozilla Public License Version 2.0", ["MPL-2.0"]),
        ("Solderpad Hardware License v 2.1", ["SHL-2.1"]),
        ("Copyright 2020 Someone. All rights reserved.", []),
    ],
)
def test_classify_recognises_license_wording(text, expected):
    assert rl.classify(text) == expected


def test_classify_reports_every_distinct_license_in_a_combined_file():
    text = (
        "1. The firmware is available under the MIT license. Permission is hereby granted, free of charge\n"
        "2. The hardware designs are available under the CERN-OHL-P v2 license.\n"
    )
    assert rl.classify(text) == ["MIT", "CERN-OHL-P-2.0"]


def test_gpl_text_that_merely_mentions_the_lesser_licence_is_still_gpl():
    text = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n... use the GNU Lesser General Public License instead of this License."
    assert rl.classify(text) == ["GPL-3.0"]


@pytest.mark.parametrize(
    "legacy, expected",
    [
        ({"key": "mit", "name": "MIT License", "spdx_id": "MIT"}, "MIT"),
        ({"spdx_id": "NOASSERTION"}, None),
        (None, None),
        ("", None),
        ([{"name": "License not found", "link": ""}], None),
        ([{"name": "MIT", "link": "https://raw.githubusercontent.com/x/y/master/LICENSE"}], "MIT"),
        ([{"name": "GNU", "link": "https://raw.githubusercontent.com/x/y/master/LICENSE"}], None),
        ([{"name": "MIT License", "link": "https://api.github.com/licenses/mit"}], "MIT"),
        ([{"name": "GNU General Public License v2.0", "link": "https://api.github.com/licenses/gpl-2.0"}], "GPL-2.0"),
    ],
)
def test_spdx_from_legacy_shapes(legacy, expected):
    assert rl.spdx_from_legacy(legacy) == expected


def test_legacy_links_are_kept_as_hints():
    legacy = [
        {"name": "GNU", "link": "https://raw.githubusercontent.com/a/b/master/LICENSE"},
        {"name": "CERN", "link": "https://raw.githubusercontent.com/a/b/master/PCB/LICENSE"},
    ]
    assert rl.legacy_paths(legacy) == ["LICENSE", "PCB/LICENSE"]


def test_repo_slug_from_source_url():
    assert rl.repo_slug("https://github.com/Owner/Repo") == "Owner/Repo"
    assert rl.repo_slug("https://github.com/Owner/Repo/") == "Owner/Repo"
    assert rl.repo_slug("https://github.com/Owner/Repo.git") == "Owner/Repo"
    assert rl.repo_slug("https://kitspace.org/boards/x") is None


def test_retrieved_at_is_rendered_as_utc_iso():
    assert rl.iso_utc("2023-08-17 17:22:53.294066") == "2023-08-17T17:22:53Z"
    assert rl.iso_utc("2023-04-30 22\u223622\u223620") == "2023-04-30T22:22:20Z"


def test_pick_shallowest_license_file_from_tree():
    paths = ["hardware/LICENSE", "LICENSE.md", "docs/COPYING", "src/main.c", "firmware/licence"]
    assert rl.license_file_candidates(paths) == ["LICENSE.md", "hardware/LICENSE", "docs/COPYING", "firmware/licence"]


def test_bundled_library_and_model_licenses_are_not_the_boards():
    paths = ["firmware/lib/QTouch/license.txt", "Libraries/3D/walter/license.txt", "kicad/footprints/LICENSE", "LICENSE"]
    assert rl.license_file_candidates(paths) == ["LICENSE"]


def test_classify_tolerates_line_breaks_inside_a_title():
    assert rl.classify("Creative Commons Attribution-ShareAlike\n4.0 International License") == ["CC-BY-SA-4.0"]


def test_license_entry_for_a_classified_license():
    res = rl.Resolution(
        spdx_id="CERN-OHL-P-2.0", name="CERN Open Hardware Licence Version 2 - Permissive", path="LICENSE",
        source_commit="abc123", method="text-match", status=rl.STATUS_LICENSED, text="...", detected_ids=["CERN-OHL-P-2.0"],
    )
    assert rl.license_entry(res) == {
        "spdx_id": "CERN-OHL-P-2.0",
        "name": "CERN Open Hardware Licence Version 2 - Permissive",
        "path": "LICENSE",
        "source_commit": "abc123",
        "detected_by": "text-match",
        "detected_ids": ["CERN-OHL-P-2.0"],
        "status": "licensed",
        "file": "LICENSE",
    }


def test_license_entry_for_an_unlicensed_board_has_no_file():
    res = rl.Resolution.unlicensed(source_commit="abc123")
    entry = rl.license_entry(res)
    assert entry["status"] == "unlicensed"
    assert entry["spdx_id"] is None
    assert entry["file"] is None


META = {
    "org": "https://github.com/j3270",
    "source": "https://github.com/j3270/1-Wire-Wing-pcb",
    "author": "j3270",
    "retrieved at": "2023-08-17 17:22:53.294066",
    "raw": "../../PCBs/1-Wire-Wing-pcb_1-Wire_Wing/raw.kicad_pcb",
    "cleaned": "../../PCBs/1-Wire-Wing-pcb_1-Wire_Wing/processed.kicad_pcb",
    "json": "../../PCBs/1-Wire-Wing-pcb_1-Wire_Wing/metadata.kicad_pcb",
    "supplementary files": "",
    "licenses": {"key": "mit", "name": "MIT License", "spdx_id": "MIT"},
    "layers": 2,
    "CAD version": "KiCad 4",
}


def test_notice_for_a_licensed_board_names_source_license_and_modification():
    res = rl.Resolution(
        spdx_id="MIT", name="MIT License", path="LICENSE", source_commit="abc123",
        method="github", status=rl.STATUS_LICENSED, text="MIT text", detected_ids=["MIT"],
    )
    notice = rl.notice_text("1-Wire-Wing-pcb_1-Wire_Wing", META, res)
    assert "# 1-Wire-Wing-pcb_1-Wire_Wing" in notice
    assert "https://github.com/j3270/1-Wire-Wing-pcb" in notice
    assert "abc123" in notice
    assert "j3270" in notice
    assert "MIT" in notice
    assert "LICENSE" in notice
    assert "2023-08-17" in notice
    assert "processed.kicad_pcb" in notice and "final.json" in notice


def test_notice_for_an_unlicensed_board_says_all_rights_reserved():
    notice = rl.notice_text("x_y", META, rl.Resolution.unlicensed(source_commit=None))
    assert "No license" in notice
    assert "all rights" in notice.lower()
    assert "not redistributable" in notice.lower()
    assert "same license" not in notice


def test_notice_for_a_missing_source_explains_the_standard_text():
    notice = rl.notice_text("x_y", META, rl.Resolution.missing("MIT", "standard MIT text"))
    assert "no longer available" in notice
    assert "standard MIT text" in notice
    assert "verbatim" not in notice


def test_write_board_writes_metadata_license_and_notice(tmp_path):
    folder = tmp_path / "PCBs" / "x_y"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text(json.dumps(META))
    res = rl.Resolution(
        spdx_id="MIT", name="MIT License", path="LICENSE", source_commit="abc123",
        method="github", status=rl.STATUS_LICENSED, text="MIT text\n", detected_ids=["MIT"],
    )
    rl.write_board(folder, META, res)
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["licenses"]["spdx_id"] == "MIT"
    assert meta["layers"] == 2
    assert (folder / "LICENSE").read_text() == "MIT text\n"
    assert (folder / "NOTICE.md").exists()


def test_write_board_for_unlicensed_removes_a_stale_license_file(tmp_path):
    folder = tmp_path / "PCBs" / "x_y"
    folder.mkdir(parents=True)
    (folder / "metadata.json").write_text(json.dumps(META))
    (folder / "LICENSE").write_text("stale")
    rl.write_board(folder, META, rl.Resolution.unlicensed(source_commit=None))
    assert not (folder / "LICENSE").exists()
    assert json.loads((folder / "metadata.json").read_text())["licenses"]["status"] == "unlicensed"


def test_rebuild_master_counts_boards_and_repos(tmp_path):
    pcbs = tmp_path / "PCBs"
    for name, source in [("a_b", "https://github.com/a/b"), ("kitspace_c", "https://github.com/c/d"), ("a_e", "https://github.com/a/b")]:
        (pcbs / name).mkdir(parents=True)
        (pcbs / name / "metadata.json").write_text(json.dumps({**META, "source": source, "licenses": {"status": "licensed", "spdx_id": "MIT"}}))
    rl.rebuild_master(pcbs)
    master = json.loads((pcbs / "master_metadata.json").read_text())
    info = master["Global Info"]
    assert info["Num. Unique pcb designs"] == 3
    assert info["Num. Unique repos"] == 2
    assert info["From Kitspace"] == 1
    assert info["Kicad source files"] == 3
    assert info["Licensed"] == 3
    assert info["Unlicensed"] == 0
    assert master["a_b"]["licenses"]["spdx_id"] == "MIT"
    assert "Global Info" in master and len(master) == 4


def test_summary_lists_counts_and_unlicensed_boards(tmp_path):
    boards = [
        ("a_b", {"licenses": {"status": "licensed", "spdx_id": "MIT"}}),
        ("c_d", {"licenses": {"status": "unlicensed", "spdx_id": None}}),
        ("e_f", {"licenses": {"status": "licensed", "spdx_id": "MIT"}}),
    ]
    text = rl.summary_text(boards)
    assert "| MIT | 2 |" in text
    assert "c_d" in text
    assert "Unlicensed | 1" in text
