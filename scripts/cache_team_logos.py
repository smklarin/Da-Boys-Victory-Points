"""Cache ESPN fantasy team logos locally for GitHub Pages.

The ESPN API returns some logo URLs that browsers cannot reliably hotlink from
GitHub Pages. This script downloads each team's current logo using the same
ESPN session cookies available to GitHub Actions, stores it under
assets/team-logos/, and rewrites dashboard JSON logo fields to use local paths.
If a remote host blocks automated downloading, an existing local team-<id>.*
asset is preserved and used as the fallback.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from calculate_victory_points import LEAGUE_ID, SEASON, fetch_league

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = ROOT / "assets" / "team-logos"
PROCESSED_PATH = ROOT / "data" / "processed" / f"{SEASON}.json"


def guess_extension(content_type: str | None, url: str) -> str:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "image/svg+xml":
        return ".svg"
    if content_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/gif":
        return ".gif"
    if content_type == "image/webp":
        return ".webp"

    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in {".svg", ".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return ".jpg" if ext == ".jpeg" else ext

    guessed = mimetypes.guess_extension(content_type) if content_type else None
    return guessed or ".img"


def existing_local_logo(team_id: int) -> str | None:
    for ext in (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"):
        path = LOGO_DIR / f"team-{team_id}{ext}"
        if path.exists():
            return f"./assets/team-logos/{path.name}"
    return None


def download_logo(url: str, team_id: int, swid: str, espn_s2: str) -> str | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://fantasy.espn.com/",
            "Cookie": f"SWID={swid}; espn_s2={espn_s2}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"WARN: team {team_id} logo download failed: {exc}")
        return None

    if not body:
        print(f"WARN: team {team_id} logo response was empty")
        return None

    ext = guess_extension(content_type, url)
    if ext == ".img":
        print(f"WARN: team {team_id} logo had unrecognized content type {content_type!r}")
        return None

    LOGO_DIR.mkdir(parents=True, exist_ok=True)

    for old in LOGO_DIR.glob(f"team-{team_id}.*"):
        old.unlink()

    path = LOGO_DIR / f"team-{team_id}{ext}"
    path.write_bytes(body)
    return f"./assets/team-logos/{path.name}"


def rewrite_processed_json(local_logos: dict[int, str]) -> None:
    if not PROCESSED_PATH.exists():
        raise RuntimeError(f"Processed season JSON not found: {PROCESSED_PATH}")

    data = json.loads(PROCESSED_PATH.read_text(encoding="utf-8"))

    for row in data.get("standings", []):
        team_id = row.get("teamId")
        if team_id in local_logos:
            row["logo"] = local_logos[team_id]

    for week in data.get("weeks", []):
        for row in week.get("teams", []):
            team_id = row.get("teamId")
            if team_id in local_logos:
                row["logo"] = local_logos[team_id]

    PROCESSED_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    swid = os.environ.get("ESPN_SWID", "")
    espn_s2 = os.environ.get("ESPN_S2", "")
    if not swid or not espn_s2:
        raise RuntimeError("ESPN_SWID and/or ESPN_S2 is missing from the environment")

    league = fetch_league()
    if league.get("id") != LEAGUE_ID:
        raise RuntimeError("Unexpected ESPN league response")

    local_logos: dict[int, str] = {}
    for team in league.get("teams") or []:
        team_id = team.get("id")
        logo_url = team.get("logo")
        if not isinstance(team_id, int) or not isinstance(logo_url, str) or not logo_url:
            continue

        local_path = download_logo(logo_url, team_id, swid, espn_s2)
        if not local_path:
            local_path = existing_local_logo(team_id)
            if local_path:
                print(f"Using existing local fallback for team {team_id}: {local_path}")

        if local_path:
            local_logos[team_id] = local_path
            print(f"Resolved team {team_id} logo -> {local_path}")

    rewrite_processed_json(local_logos)
    print(f"Resolved {len(local_logos)} team logos.")

    if not local_logos:
        raise RuntimeError("No team logos could be resolved")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
