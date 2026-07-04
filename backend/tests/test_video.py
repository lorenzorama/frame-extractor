from unittest.mock import patch, MagicMock

import pytest

from app.video import get_video_duration, download_video, extract_frame, compute_timestamps


def test_compute_timestamps_interval_only():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=None)
    assert result == [0.0, 5.0, 9.5]


def test_compute_timestamps_merges_manual_and_dedupes():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=[5.0, 7.5])
    assert result == [0.0, 5.0, 7.5, 9.5]


def test_compute_timestamps_rejects_out_of_range():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=[15.0])


def test_compute_timestamps_requires_interval_or_manual():
    with pytest.raises(ValueError):
        compute_timestamps(duration=10.0, interval_seconds=None, manual_timestamps=None)


def test_compute_timestamps_never_samples_at_or_past_duration():
    # ffmpeg cannot reliably decode a frame exactly at (or past) a video's
    # reported duration -- no frame exists there, so extraction fails.
    # Regression test for a real job failure: seeking to a video's exact
    # reported duration (62.98s) produced zero frames and a hard ffmpeg
    # encoder error, while seeking to 62.9s succeeded.
    result = compute_timestamps(duration=62.98, interval_seconds=None, manual_timestamps=[62.98])
    assert result == [62.48]
    assert result[-1] < 62.98


def test_compute_timestamps_interval_final_timestamp_capped_below_duration():
    result = compute_timestamps(duration=10.0, interval_seconds=5.0, manual_timestamps=None)
    assert result[-1] < 10.0


def test_compute_timestamps_very_short_duration_does_not_go_negative():
    result = compute_timestamps(duration=0.2, interval_seconds=5.0, manual_timestamps=None)
    assert result == [0.0]


@patch("app.video.subprocess.run")
def test_get_video_duration_parses_yt_dlp_json(mock_run):
    mock_run.return_value = MagicMock(stdout='{"duration": 123.4}', returncode=0)
    duration = get_video_duration("https://youtube.com/watch?v=abc")
    assert duration == 123.4
    assert mock_run.called


@patch("app.video.subprocess.run")
def test_download_video_invokes_yt_dlp(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    download_video("https://youtube.com/watch?v=abc", "/data/1/1/source.mp4")
    args = mock_run.call_args[0][0]
    assert "yt-dlp" in args
    assert "/data/1/1/source.mp4" in args
    assert "--merge-output-format" in args
    assert "mp4" in args
    assert "-f" in args
    assert "bv*+ba/b" in args


@patch("app.video.subprocess.run")
def test_extract_frame_invokes_ffmpeg(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    extract_frame("/data/1/1/source.mp4", 5.0, "/data/1/1/frames/5.0.jpg")
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-q:v" in args
    assert "3" in args
