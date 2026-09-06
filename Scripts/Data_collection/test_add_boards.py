import json

import add_boards as ab

BOARD = """(kicad_pcb (version 20221018) (generator pcbnew)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts") (width 0.1))
  (segment (start 1 1) (end 2 2) (width 0.25) (layer "F.Cu") (net 1))
  (zone (net 1) (net_name "GND") (layer "F.Cu")
    (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10)))
    (filled_polygon (layer "F.Cu") (pts (xy 0.5 0.5) (xy 9 0.5) (xy 9 9)))
  )
)
"""


def test_folder_name_joins_repo_and_stem_and_drops_awkward_characters():
    assert ab.folder_name("Hanqaqa/Easyduino", "ESP32S3/Easyduino_ESP32S3.kicad_pcb") == "Easyduino_Easyduino_ESP32S3"
    assert ab.folder_name("RespiraWorks/Ventilator", "pcb/x/pressure_mpx5700ap,gp.kicad_pcb") == "Ventilator_pressure_mpx5700ap_gp"
    assert ab.folder_name("Seeed-Studio/OSHW-reCamera-Series", "a/reCamera Basically Board.kicad_pcb") == "OSHW-reCamera-Series_reCamera_Basically_Board"


def test_board_facts_read_from_the_file_text():
    facts = ab.board_facts(BOARD)
    assert facts == {"format_version": 20221018, "generator_version": None, "copper_layers": 2, "nets": 2, "segments": 1, "has_outline": True}


def test_board_facts_take_the_generator_version_when_present():
    text = BOARD.replace('(generator pcbnew)', '(generator "pcbnew") (generator_version "8.0")')
    assert ab.board_facts(text)["generator_version"] == "8.0"


def test_kicad_release_maps_format_dates_and_prefers_the_generator_version():
    assert ab.kicad_release({"format_version": 20221018, "generator_version": None}) == "7"
    assert ab.kicad_release({"format_version": 20260206, "generator_version": "10.0"}) == "10.0"
    assert ab.kicad_release({"format_version": 4, "generator_version": None}) == "4"


def test_validation_rejects_unrouted_or_outline_less_boards():
    assert ab.rejection(ab.board_facts(BOARD)) is None
    assert "routed" in ab.rejection(ab.board_facts(BOARD.replace("(segment", "(xsegment")))
    assert "outline" in ab.rejection(ab.board_facts(BOARD.replace('"Edge.Cuts"', '"Cmts.User"')))
    assert "net" in ab.rejection(ab.board_facts(BOARD.replace('(net 2 "VCC")', "")))


def test_unfill_zones_drops_fills_but_keeps_the_zone_outline():
    out = ab.unfill_zones(BOARD)
    assert "filled_polygon" not in out
    assert "(polygon (pts (xy 0 0) (xy 10 0) (xy 10 10)))" in out
    assert "(segment (start 1 1)" in out
    assert out.count("(") == out.count(")")


def test_write_board_creates_the_folder_layout(tmp_path):
    pcbs = tmp_path / "PCBs"
    name = ab.write_board(pcbs, "Gekkio/gb-hardware", "GB-CART32K-A/GB-CART32K-A.kicad_pcb", "abc123", BOARD, "2026-09-06 12:00:00.000000")
    folder = pcbs / name
    assert name == "gb-hardware_GB-CART32K-A"
    assert (folder / "raw.kicad_pcb").read_text() == BOARD
    assert "filled_polygon" not in (folder / "processed.kicad_pcb").read_text()
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["org"] == "https://github.com/Gekkio"
    assert meta["source"] == "https://github.com/Gekkio/gb-hardware"
    assert meta["author"] == "Gekkio"
    assert meta["retrieved at"] == "2026-09-06 12:00:00.000000"
    assert meta["raw"] == f"../../PCBs/{name}/raw.kicad_pcb"
    assert meta["cleaned"] == f"../../PCBs/{name}/processed.kicad_pcb"
    assert meta["json"] == ""
    assert meta["licenses"] is None
    assert meta["layers"] == 2
    assert meta["CAD version"] == "KiCad 20221018"
    assert meta["kicad_version"] == "7"
    assert meta["source_path"] == "GB-CART32K-A/GB-CART32K-A.kicad_pcb"
    assert meta["source_commit"] == "abc123"


def test_write_board_keeps_a_project_file_when_given(tmp_path):
    pcbs = tmp_path / "PCBs"
    name = ab.write_board(pcbs, "o/r", "b.kicad_pcb", "sha", BOARD, "2026-09-06 12:00:00.000000", project='{"meta": {}}')
    assert (pcbs / name / "raw.kicad_pro").read_text() == '{"meta": {}}'
    meta = json.loads((pcbs / name / "metadata.json").read_text())
    assert meta["supplementary files"] == f"../../PCBs/{name}/raw.kicad_pro"


def test_write_board_without_a_project_file_leaves_supplementary_empty(tmp_path):
    pcbs = tmp_path / "PCBs"
    name = ab.write_board(pcbs, "o/r", "b.kicad_pcb", "sha", BOARD, "2026-09-06 12:00:00.000000")
    assert not (pcbs / name / "raw.kicad_pro").exists()
    assert json.loads((pcbs / name / "metadata.json").read_text())["supplementary files"] == ""


def test_folder_name_can_include_the_parent_directory():
    assert ab.folder_name("m/CATs", "Modules/Slim Line/Rectifier SMD/Electronics/Main/Rectifier Main.kicad_pcb", parents=1) == "CATs_Main_Rectifier_Main"
    assert ab.folder_name("m/CATs", "Modules/Slim Line/Rectifier SMD/Electronics/Main/Rectifier Main.kicad_pcb", parents=2) == "CATs_Electronics_Main_Rectifier_Main"


def test_unique_folder_name_disambiguates_same_named_boards(tmp_path):
    pcbs = tmp_path / "PCBs"
    taken = set()
    first = ab.unique_folder_name(pcbs, "m/CATs", "Rectifier/Main/Rectifier Main.kicad_pcb", taken)
    taken.add(first)
    second = ab.unique_folder_name(pcbs, "m/CATs", "Rectifier SMD/Main/Rectifier Main.kicad_pcb", taken)
    assert first == "CATs_Rectifier_Main" and second == "CATs_Main_Rectifier_Main"


def test_unique_folder_name_keeps_a_folder_that_already_holds_the_same_board(tmp_path):
    pcbs = tmp_path / "PCBs"
    ab.write_board(pcbs, "o/r", "a/b.kicad_pcb", "sha", BOARD, "2026-09-06 12:00:00.000000")
    assert ab.unique_folder_name(pcbs, "o/r", "a/b.kicad_pcb", set()) == "r_b"
    assert ab.unique_folder_name(pcbs, "o/r", "other/b.kicad_pcb", set()) == "r_other_b"


def test_unique_folder_name_walks_up_as_far_as_needed(tmp_path):
    taken = set()
    names = []
    for path in ["v0.1/kicad/pcb.kicad_pcb", "v0.2/kicad/pcb.kicad_pcb", "v0.3/kicad/pcb.kicad_pcb"]:
        names.append(ab.unique_folder_name(tmp_path / "PCBs", "j/oasis", path, taken))
        taken.add(names[-1])
    assert names == ["oasis_pcb", "oasis_kicad_pcb", "oasis_v0.3_kicad_pcb"]


def test_parse_list_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / "list.txt"
    f.write_text("# header\nowner/repo\tdir/a.kicad_pcb\n\nowner/repo\tb.kicad_pcb\n")
    assert ab.parse_list(f) == [("owner/repo", "dir/a.kicad_pcb"), ("owner/repo", "b.kicad_pcb")]
