"""Stage 0 (APK-as-input): capture one gameplay video per target game.

Deterministic capture: for each game in GAMES, yt-dlp searches YouTube and
takes the first result, then downloads the video (<=480p, muted) into
videos/ for frame sampling by spec_writer.py. Sources are recorded in
sources.json. No manual picking, no emulator, no APK download.

Usage: python tools/apk_input/fetch_sources.py [--repo-root PATH]
"""

import json
import sys
from pathlib import Path

from yt_dlp import YoutubeDL

REPO = Path(__file__).resolve().parents[2]

# One search phrase per game — first hit wins, recorded verbatim in sources.json.
GAMES = {
    "hay_day": "Hay Day gameplay",
    "township": "Township gameplay",
    "family_farm_adventure": "Family Farm Adventure gameplay",
}


def _ffmpeg_location() -> str | None:
    """Locate a usable ffmpeg (imageio-ffmpeg ships a static binary)."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def fetch_one(slug: str, query: str, out_dir: Path) -> dict:
    """Search YouTube, download one video, return its metadata."""
    ydl_opts = {
        # h264 (avc1) video-only single stream: frame sampling needs no audio,
        # and AV1 streams are not decodable by the bundled opencv build.
        "format": (
            "b[vcodec^=avc1][height<=480]/bv*[vcodec^=avc1][height<=480]+ba/b[height<=480]/b"
        ),
        "ffmpeg_location": _ffmpeg_location() or "ffmpeg",
        "outtmpl": str(out_dir / f"{slug}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch1:{query}", download=True)["entries"][0]

    video_path = next(out_dir.glob(f"{slug}.*"))
    return {
        "slug": slug,
        "query": query,
        "video_id": info["id"],
        "url": info["webpage_url"],
        "title": info["title"],
        "channel": info.get("channel"),
        "duration_s": info.get("duration"),
        "local_file": video_path.name,
    }


def main() -> None:
    videos_dir = REPO / "tools" / "apk_input" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    sources_path = Path(__file__).resolve().parent / "sources.json"

    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {}
    for slug, query in GAMES.items():
        if slug in sources:
            print(f"[fetch_sources] {slug}: already captured -> {sources[slug]['url']}")
            continue
        print(f"[fetch_sources] {slug}: searching '{query}' ...")
        sources[slug] = fetch_one(slug, query, videos_dir)
        sources_path.write_text(
            json.dumps(sources, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"[fetch_sources] {slug}: {sources[slug]['title']} ({sources[slug]['url']})")


if __name__ == "__main__":
    sys.exit(main())
