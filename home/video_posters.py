import hashlib
import subprocess


def video_source_signature(document):
    """Return a content hash so a cached poster follows changes to its video."""
    digest = hashlib.sha256()
    with document.file.open("rb") as video_file:
        for chunk in video_file.chunks():
            digest.update(chunk)
    return digest.hexdigest()


def extract_video_poster(document):
    """Extract one JPEG frame, preferring a point shortly after the opening."""
    video_path = document.file.path
    errors = []
    for timestamp in ("1", "0"):
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                timestamp,
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-vf",
                "scale=w='min(1600,iw)':h=-2",
                "-q:v",
                "3",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
        errors.append(result.stderr.decode("utf-8", errors="replace")[-500:])

    raise RuntimeError("FFmpeg could not extract a video frame: " + " | ".join(errors))
