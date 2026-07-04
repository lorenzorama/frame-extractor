import json
import subprocess


def compute_timestamps(
    duration: float,
    interval_seconds: float | None,
    manual_timestamps: list[float] | None,
) -> list[float]:
    if interval_seconds is None and not manual_timestamps:
        raise ValueError("Must provide interval_seconds and/or manual_timestamps")

    timestamps: set[float] = set()

    if interval_seconds is not None:
        t = 0.0
        while t < duration:
            timestamps.add(round(t, 3))
            t += interval_seconds
        timestamps.add(round(duration, 3))

    for t in manual_timestamps or []:
        if t < 0 or t > duration:
            raise ValueError(f"Timestamp {t} is outside video duration {duration}")
        timestamps.add(round(t, 3))

    return sorted(timestamps)


def get_video_duration(url: str) -> float:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "-j", url],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["duration"])


def download_video(url: str, dest_path: str) -> None:
    subprocess.run(
        [
            "yt-dlp", "--no-warnings",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", dest_path,
            url,
        ],
        check=True,
    )


def extract_frame(video_path: str, timestamp: float, dest_path: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            dest_path,
        ],
        check=True,
        capture_output=True,
    )
