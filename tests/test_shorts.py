import pytest

from nightcut import shorts


def test_caption_backend_uses_libass_when_available(monkeypatch):
    monkeypatch.setattr(shorts, "ffmpeg_filters", lambda: {"scale", "subtitles"})
    assert shorts._caption_backend({"caption_backend": "auto"}) == "subtitles"


def test_caption_backend_uses_portable_fallback_without_libass(monkeypatch):
    monkeypatch.setattr(shorts, "ffmpeg_filters", lambda: {"scale"})
    assert shorts._caption_backend({"caption_backend": "auto"}) == "png_video"


def test_caption_backend_rejects_unknown_value():
    with pytest.raises(ValueError, match="caption_backend"):
        shorts._caption_backend({"caption_backend": "one_png_per_word"})


def _tracks(tmp_path, titles=(("Mix", 2), ("Mic", 1), ("Game", 2), ("Discord", 2), ("Musik", 2))):
    from nightcut.media import AudioStream, MediaInfo
    from nightcut.tracks import timeline_tracks

    streams = [AudioStream(i + 1, i, t, ch, 48000) for i, (t, ch) in enumerate(titles)]
    rec = MediaInfo(tmp_path / "rec.mkv", 600.0, 1920, 1080, 60.0, streams)
    return timeline_tracks(rec, {"mic": streams[1], "game": streams[2], "party": streams[3]}, mix=streams[0])


def test_short_keeps_every_single_track_but_not_the_mix_of_the_recording(tmp_path):
    single = shorts.separate_tracks(_tracks(tmp_path), {})
    assert [t.label for t in single] == ["MIC", "GAME", "PARTY", "Musik"]


def test_short_with_one_track_or_switched_off_stays_a_plain_file(tmp_path):
    audio = _tracks(tmp_path)
    assert shorts.separate_tracks(audio, {"separate_audio": False}) == []
    assert shorts.separate_tracks(audio[:2], {}) == []  # the mix and the mic: nothing to balance
    assert shorts._audio_outputs([]) == ["-map", "[a]"]


def test_short_audio_finished_mix_first_and_default(tmp_path):
    args = shorts._audio_outputs(shorts.separate_tracks(_tracks(tmp_path), {}))
    assert [args[i + 1] for i, a in enumerate(args) if a == "-map"] == ["[a]", "0:2", "0:3", "0:4", "0:5"]
    assert [args[i + 1] for i, a in enumerate(args) if a.startswith("-disposition")] == ["default", "0", "0", "0", "0"]
    assert [a for a in args if a.startswith("title=")] == ["title=MIX", "title=MIC", "title=GAME", "title=PARTY",
                                                           "title=Musik"]


def test_short_timeline_has_single_tracks_on_and_mix_off(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET

    from nightcut import export_xmeml
    from nightcut.media import AudioStream, MediaInfo

    single = shorts.separate_tracks(_tracks(tmp_path), {})
    in_file = [AudioStream(i + 1, i, f"audio{i}", ch, 48000) for i, ch in enumerate([2, 1, 2, 2, 2])]
    made = lambda p: MediaInfo(p, 42.0, 1080, 1920, 30.0, in_file)  # noqa: E731
    monkeypatch.setattr(shorts, "probe", made)
    monkeypatch.setattr(export_xmeml, "probe", made)
    out = shorts.write_timeline(tmp_path / "short_01.mp4", 1, "Clutch", single, {"export": {"facecam_pip": {}}},
                                "rec Short 01")

    assert out == tmp_path / "short_01.xml"
    seq = ET.parse(out).getroot().find("sequence")
    assert seq.findtext("name") == "rec Short 01"
    assert (seq.findtext("media/video/format/samplecharacteristics/width"),
            seq.findtext("media/video/format/samplecharacteristics/height")) == ("1080", "1920")
    assert seq.findtext("duration") == str(42 * 30)
    a_tracks = seq.findall("media/audio/track")
    assert [t.find("clipitem").findtext("name") for t in a_tracks] == [
        "01 Clutch MIX", "01 Clutch MIC", "01 Clutch GAME", "01 Clutch PARTY", "01 Clutch Musik"]
    assert [t.find("clipitem").findtext("enabled") for t in a_tracks] == ["FALSE", "TRUE", "TRUE", "TRUE", "TRUE"]
    assert [t.find("clipitem").findtext("sourcetrack/trackindex") for t in a_tracks] == ["1", "2", "3", "4", "5"]