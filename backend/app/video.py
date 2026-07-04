import json
import subprocess

# ffmpeg cannot reliably decode a frame exactly at (or past) a video's
# reported duration -- no frame exists there, and its fallback path for
# "no filtered frames" fails to initialize the encoder without real frame
# data. Cap sampling this far short of the reported duration.
SAFE_END_BUFFER_SECONDS = 0.5


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(
            f"Command {args!r} failed with exit code {exc.returncode}: {stderr or '(no stderr output)'}"
        ) from exc


def compute_timestamps(
    duration: float,
    interval_seconds: float | None,
    manual_timestamps: list[float] | None,
) -> list[float]:
    if interval_seconds is None and not manual_timestamps:
        raise ValueError("Must provide interval_seconds and/or manual_timestamps")

    safe_end = max(0.0, duration - SAFE_END_BUFFER_SECONDS)

    timestamps: set[float] = set()

    if interval_seconds is not None:
        t = 0.0
        while t < safe_end:
            timestamps.add(round(t, 3))
            t += interval_seconds
        timestamps.add(round(safe_end, 3))

    for t in manual_timestamps or []:
        if t < 0 or t > duration:
            raise ValueError(f"Timestamp {t} is outside video duration {duration}")
        timestamps.add(round(min(t, safe_end), 3))

    return sorted(timestamps)


def get_video_duration(url: str) -> float:
    result = _run(["yt-dlp", "--no-warnings", "--no-playlist", "-j", url])
    data = json.loads(result.stdout)
    return float(data["duration"])


def download_video(url: str, dest_path: str) -> None:
    _run(
        [
            "yt-dlp", "--no-warnings", "--no-playlist",
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", dest_path,
            url,
        ]
    )


def extract_frame(video_path: str, timestamp: float, dest_path: str) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "3",
            dest_path,
        ]
    )
