import json

from nightcut import workdir


def _rec(folder, name="rec.mkv", size=1000):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"x" * size)
    return path


def _cfg(**changes):
    cfg = {"output_dir": "./output", "mode": "highlights", "gpus": {"use": "auto"}, "pricing_file": None,
           "editor": {"target_minutes": 14, "fill": None}, "profile": {"name": "bf6"}}
    return {**cfg, **changes}


def _start(out, name, project, stages=("audio",)):
    """What a run does: take a folder and note in run.json what it is made from."""
    folder, note = workdir.choose(out, name, project)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps({"stages": {s: {} for s in stages}, "project": project}))
    return folder, note


def test_fingerprint_changes_with_settings_but_not_with_folder_gpus_or_fill(tmp_path):
    rec = _rec(tmp_path / "in")
    base = workdir.fingerprint([rec], _cfg(), "highlights")
    same = workdir.fingerprint([rec], _cfg(output_dir="D:/out", gpus={"use": 1}, pricing_file="p.yaml",
                                           editor={"target_minutes": 14, "fill": True}), "highlights")
    assert same == base
    assert workdir.fingerprint([rec], _cfg(editor={"target_minutes": 8, "fill": None}), "highlights") != base
    assert workdir.fingerprint([rec], _cfg(profile={"name": "bf2042"}), "highlights") != base


def test_first_run_takes_the_name_of_the_recording(tmp_path):
    project = workdir.fingerprint([_rec(tmp_path / "in")], _cfg(), "highlights")
    assert workdir.choose(tmp_path / "out", "rec", project) == (tmp_path / "out" / "rec", "")
    (tmp_path / "out" / "rec").mkdir(parents=True)  # an empty folder is free as well
    assert workdir.choose(tmp_path / "out", "rec", project) == (tmp_path / "out" / "rec", "")


def test_same_run_goes_on_in_its_folder(tmp_path):
    out = tmp_path / "out"
    project = workdir.fingerprint([_rec(tmp_path / "in")], _cfg(), "highlights")
    first, _ = _start(out, "rec", project)
    folder, note = workdir.choose(out, "rec", project)
    assert folder == first == out / "rec"
    assert "Going on" in note


def test_other_recording_with_the_same_name_gets_its_own_folder(tmp_path):
    out = tmp_path / "out"
    _start(out, "rec", workdir.fingerprint([_rec(tmp_path / "monday")], _cfg(), "highlights"))
    other = workdir.fingerprint([_rec(tmp_path / "tuesday", size=2000)], _cfg(), "highlights")
    folder, note = _start(out, "rec", other)
    assert folder == out / "rec_2"
    assert "another recording" in note and "--force" not in note
    # an interrupted second run goes on in rec_2 and does not open rec_3
    assert workdir.choose(out, "rec", other)[0] == out / "rec_2"
    third = workdir.fingerprint([_rec(tmp_path / "friday", size=3000)], _cfg(), "highlights")
    assert workdir.choose(out, "rec", third)[0] == out / "rec_3"
    # forcing a stage does not get a run into the folder of another recording
    assert workdir.choose(out, "rec", third, forced=True)[0] == out / "rec_3"


def test_other_settings_get_a_new_folder_unless_a_stage_is_forced(tmp_path):
    out, rec = tmp_path / "out", _rec(tmp_path / "in")
    _start(out, "rec", workdir.fingerprint([rec], _cfg(), "highlights"))
    changed = workdir.fingerprint([rec], _cfg(editor={"target_minutes": 8}), "highlights")
    folder, note = workdir.choose(out, "rec", changed)
    assert folder == out / "rec_2"
    assert "other settings" in note and "--force" in note
    folder, note = workdir.choose(out, "rec", changed, forced=True)
    assert folder == out / "rec"
    assert "other settings" in note


def test_other_mode_and_other_version_get_a_new_folder(tmp_path, monkeypatch):
    out, rec = tmp_path / "out", _rec(tmp_path / "in")
    project = workdir.fingerprint([rec], _cfg(), "highlights")
    _start(out, "rec", project)
    assert workdir.choose(out, "rec", workdir.fingerprint([rec], _cfg(), "letsplay"))[0] == out / "rec_2"
    monkeypatch.setattr(workdir, "__version__", "99.0.0")
    folder, note = workdir.choose(out, "rec", workdir.fingerprint([rec], _cfg(), "highlights"))
    assert folder == out / "rec_2"
    assert "nightcut " + project["nightcut"] in note


def test_more_recordings_in_a_series_are_another_run(tmp_path):
    out = tmp_path / "out"
    a, b = _rec(tmp_path / "in", "a.mkv"), _rec(tmp_path / "in", "b.mkv", 2000)
    _start(out, "serie", workdir.fingerprint([a], _cfg(), "letsplay"))
    assert workdir.choose(out, "serie", workdir.fingerprint([a, b], _cfg(), "letsplay"))[0] == out / "serie_2"


def test_folder_of_an_older_nightcut_or_of_someone_else(tmp_path):
    out = tmp_path / "out"
    project = workdir.fingerprint([_rec(tmp_path / "in")], _cfg(), "highlights")
    old = out / "rec"
    old.mkdir(parents=True)
    (old / "notes.txt").write_text("mine")
    folder, note = workdir.choose(out, "rec", project, forced=True)  # not a run: never touched
    assert folder == out / "rec_2" and "not from a nightcut run" in note
    (old / "run.json").write_text(json.dumps({"stages": {"audio": {}}}))  # run.json of nightcut <= 0.3.1
    folder, note = workdir.choose(out, "rec", project)
    assert folder == out / "rec_2" and "older nightcut" in note
    assert workdir.choose(out, "rec", project, forced=True)[0] == old
    (old / "run.json").write_text("{ broken")
    assert workdir.choose(out, "rec", project, forced=True)[0] == out / "rec_2"


def test_other_names_that_only_look_alike_are_ignored(tmp_path):
    out = tmp_path / "out"
    project = workdir.fingerprint([_rec(tmp_path / "in")], _cfg(), "highlights")
    for name in ("rec_tracks", "rec_letsplay", "rec_1"):
        (out / name).mkdir(parents=True)
        (out / name / "x.txt").write_text("x")
    assert workdir.choose(out, "rec", project)[0] == out / "rec"


def test_missing_files_only_inside_the_run_folder(tmp_path):
    work = tmp_path / "out" / "rec"
    (work / "media").mkdir(parents=True)
    there = work / "media" / "clip_01.mp4"
    there.write_bytes(b"x")
    gone = work / "media" / "clip_02.mp4"
    result = [{"gameplay_file": str(there), "facecam_file": None, "title": "/ not a file", "n": 1},
              {"gameplay_file": str(gone), "source": str(tmp_path / "elsewhere" / "rec.mkv")}]
    assert workdir.missing_files(result, work) == [gone]
    assert workdir.missing_files({"text": "hello", "n": 3}, work) == []
