"""Validate ESPN fantasy league team and matchup data.

This script is intended to run in GitHub Actions. It reads ESPN_SWID and
ESPN_S2 from the environment, requests the league data, and prints only
non-secret league/team/matchup fields needed to validate the future VP
pipeline.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

LEAGUE_ID = 1289630
SEASON = 2026
WEEKS_TO_VALIDATE = (1, 2)


def team_display_name(team: dict) -> str:
    """Return ESPN's current human-readable team name with fallbacks."""
    name = (team.get("name") or "").strip()
    if name:
        return name

    location = (team.get("location") or "").strip()
    nickname = (team.get("nickname") or "").strip()
    fallback = f"{location} {nickname}".strip()
    return fallback or f"Team {team.get('id', '?')}"


def score(side: dict) -> float | None:
    value = side.get("totalPoints")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def main() -> int:
    swid = os.environ.get("ESPN_SWID", "")
    espn_s2 = os.environ.get("ESPN_S2", "")

    if not swid or not espn_s2:
        print("ERROR: ESPN_SWID and/or ESPN_S2 is missing from the environment.")
        return 1

    url = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
        f"seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
        "?view=mTeam&view=mMatchup&view=mMatchupScore&view=mSettings&view=mStatus"
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Cookie": f"SWID={swid}; espn_s2={espn_s2}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status_code = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        print(f"ERROR: ESPN returned HTTP {exc.code}.")
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: ESPN request failed: {exc.reason}")
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("ERROR: ESPN response was not valid JSON.")
        return 1

    print("=" * 72)
    print("ESPN DATA VALIDATION")
    print("=" * 72)
    print(f"HTTP status: {status_code}")
    print(f"League ID: {data.get('id')}")
    print(f"Season ID: {data.get('seasonId')}")

    status = data.get("status") or {}
    print("\nESPN STATUS")
    print(f"  currentMatchupPeriod: {status.get('currentMatchupPeriod')}")
    print(f"  latestScoringPeriod: {status.get('latestScoringPeriod')}")
    print(f"  finalScoringPeriod: {status.get('finalScoringPeriod')}")
    print(f"  isActive: {status.get('isActive')}")

    teams = data.get("teams") or []
    team_by_id: dict[int, dict] = {
        int(team["id"]): team
        for team in teams
        if isinstance(team, dict) and isinstance(team.get("id"), int)
    }

    print(f"\nTEAMS ({len(team_by_id)})")
    print("-" * 72)
    for team_id in sorted(team_by_id):
        team = team_by_id[team_id]
        name = team_display_name(team)
        abbrev = team.get("abbrev") or "-"
        logo_available = bool(team.get("logo"))
        print(
            f"ID {team_id:>2} | {name} | abbrev={abbrev} | "
            f"logo={'yes' if logo_available else 'no'}"
        )

    schedule = data.get("schedule") or []

    for week in WEEKS_TO_VALIDATE:
        matchups = [
            matchup
            for matchup in schedule
            if isinstance(matchup, dict)
            and matchup.get("matchupPeriodId") == week
        ]

        print(f"\nWEEK {week} MATCHUPS ({len(matchups)})")
        print("-" * 72)

        if not matchups:
            print("No matchups returned for this week.")
            continue

        for index, matchup in enumerate(matchups, start=1):
            home = matchup.get("home") or {}
            away = matchup.get("away") or {}
            home_id = home.get("teamId")
            away_id = away.get("teamId")

            home_team = team_by_id.get(home_id, {})
            away_team = team_by_id.get(away_id, {})
            home_name = team_display_name(home_team) if home_team else f"Team {home_id}"
            away_name = team_display_name(away_team) if away_team else f"Team {away_id}"

            home_score = score(home)
            away_score = score(away)

            if home_score is not None and away_score is not None:
                if home_score > away_score:
                    calculated_winner = home_name
                elif away_score > home_score:
                    calculated_winner = away_name
                else:
                    calculated_winner = "TIE / NOT YET SCORED"
            else:
                calculated_winner = "SCORE UNAVAILABLE"

            espn_winner = matchup.get("winner") or "UNDECIDED"

            home_score_text = "N/A" if home_score is None else f"{home_score:.2f}"
            away_score_text = "N/A" if away_score is None else f"{away_score:.2f}"

            print(f"Matchup {index}:")
            print(f"  Away: ID {away_id} | {away_name} | {away_score_text}")
            print(f"  Home: ID {home_id} | {home_name} | {home_score_text}")
            print(f"  ESPN winner flag: {espn_winner}")
            print(f"  Score-derived winner: {calculated_winner}")

    # Basic validation gates for the future app pipeline.
    errors: list[str] = []
    if status_code != 200:
        errors.append(f"HTTP status was {status_code}, expected 200")
    if data.get("id") != LEAGUE_ID:
        errors.append("League ID did not match")
    if data.get("seasonId") != SEASON:
        errors.append("Season ID did not match")
    if len(team_by_id) != 10:
        errors.append(f"Expected 10 teams, found {len(team_by_id)}")

    week_one = [m for m in schedule if m.get("matchupPeriodId") == 1]
    if len(week_one) != 5:
        errors.append(f"Expected 5 Week 1 matchups, found {len(week_one)}")

    print("\n" + "=" * 72)
    if errors:
        print("VALIDATION RESULT: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("VALIDATION RESULT: PASS")
    print("Team ID -> team name mapping and matchup structures are available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
