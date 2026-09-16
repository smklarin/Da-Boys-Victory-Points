"""Calculate weekly Victory Points from ESPN fantasy football data.

Rules for Da Boys:
- Matchup win: +2 VP
- Weekly scoring rank 1-3: +2 VP
- Weekly scoring rank 4-6: +1 VP
- Weekly scoring rank 7-10: +0 VP

The script intentionally stops if a tie occurs exactly across a scoring-tier
boundary (3rd/4th or 6th/7th), or if an ESPN matchup is tied, because the
league's tie policy has not yet been defined.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

LEAGUE_ID = 1289630
SEASON = 2026
EXPECTED_TEAMS = 10
EXPECTED_MATCHUPS = 5


def team_display_name(team: dict) -> str:
    name = (team.get("name") or "").strip()
    if name:
        return name
    location = (team.get("location") or "").strip()
    nickname = (team.get("nickname") or "").strip()
    fallback = f"{location} {nickname}".strip()
    return fallback or f"Team {team.get('id', '?')}"


def fetch_league() -> dict:
    swid = os.environ.get("ESPN_SWID", "")
    espn_s2 = os.environ.get("ESPN_S2", "")
    if not swid or not espn_s2:
        raise RuntimeError("ESPN_SWID and/or ESPN_S2 is missing from the environment")

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
            if response.status != 200:
                raise RuntimeError(f"ESPN returned HTTP {response.status}")
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ESPN returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ESPN request failed: {exc.reason}") from exc


def competition_ranks(sorted_scores: list[tuple[int, float]]) -> dict[int, int]:
    """Return standard competition ranks (1, 2, 2, 4...) keyed by team ID."""
    ranks: dict[int, int] = {}
    previous_score: float | None = None
    previous_rank = 0
    for position, (team_id, points) in enumerate(sorted_scores, start=1):
        if previous_score is None or points != previous_score:
            previous_rank = position
            previous_score = points
        ranks[team_id] = previous_rank
    return ranks


def scoring_vp(rank: int) -> int:
    if rank <= 3:
        return 2
    if rank <= 6:
        return 1
    return 0


def calculate_week(data: dict, week: int) -> dict:
    teams = data.get("teams") or []
    team_by_id = {
        int(team["id"]): team
        for team in teams
        if isinstance(team, dict) and isinstance(team.get("id"), int)
    }
    if len(team_by_id) != EXPECTED_TEAMS:
        raise RuntimeError(
            f"Expected {EXPECTED_TEAMS} teams but ESPN returned {len(team_by_id)}"
        )

    matchups = [
        matchup
        for matchup in (data.get("schedule") or [])
        if isinstance(matchup, dict) and matchup.get("matchupPeriodId") == week
    ]
    if len(matchups) != EXPECTED_MATCHUPS:
        raise RuntimeError(
            f"Expected {EXPECTED_MATCHUPS} matchups in Week {week}, found {len(matchups)}"
        )

    # Only finalized ESPN matchups are safe to process.
    undecided = [m for m in matchups if (m.get("winner") or "UNDECIDED") == "UNDECIDED"]
    if undecided:
        raise RuntimeError(
            f"Week {week} is not finalized: {len(undecided)} matchup(s) are UNDECIDED"
        )

    results: dict[int, dict] = {}
    seen_team_ids: set[int] = set()

    for matchup in matchups:
        winner_flag = matchup.get("winner")
        if winner_flag not in {"HOME", "AWAY"}:
            raise RuntimeError(
                f"Week {week} contains matchup winner flag {winner_flag!r}; "
                "matchup-tie VP rules are not yet defined"
            )

        home = matchup.get("home") or {}
        away = matchup.get("away") or {}
        home_id = home.get("teamId")
        away_id = away.get("teamId")
        home_points = home.get("totalPoints")
        away_points = away.get("totalPoints")

        if not isinstance(home_id, int) or not isinstance(away_id, int):
            raise RuntimeError(f"Week {week} matchup is missing a numeric team ID")
        if not isinstance(home_points, (int, float)) or not isinstance(away_points, (int, float)):
            raise RuntimeError(f"Week {week} matchup is missing a numeric score")

        if home_id in seen_team_ids or away_id in seen_team_ids:
            raise RuntimeError(f"A team appears more than once in Week {week}")
        seen_team_ids.update({home_id, away_id})

        home_team = team_by_id[home_id]
        away_team = team_by_id[away_id]
        home_win = winner_flag == "HOME"
        away_win = winner_flag == "AWAY"

        results[home_id] = {
            "teamId": home_id,
            "teamName": team_display_name(home_team),
            "abbrev": home_team.get("abbrev"),
            "logo": home_team.get("logo"),
            "points": float(home_points),
            "opponentId": away_id,
            "opponentName": team_display_name(away_team),
            "opponentPoints": float(away_points),
            "result": "W" if home_win else "L",
            "matchupVP": 2 if home_win else 0,
        }
        results[away_id] = {
            "teamId": away_id,
            "teamName": team_display_name(away_team),
            "abbrev": away_team.get("abbrev"),
            "logo": away_team.get("logo"),
            "points": float(away_points),
            "opponentId": home_id,
            "opponentName": team_display_name(home_team),
            "opponentPoints": float(home_points),
            "result": "W" if away_win else "L",
            "matchupVP": 2 if away_win else 0,
        }

    if len(seen_team_ids) != EXPECTED_TEAMS:
        raise RuntimeError(
            f"Week {week} includes {len(seen_team_ids)} unique teams; expected {EXPECTED_TEAMS}"
        )

    sorted_scores = sorted(
        ((team_id, row["points"]) for team_id, row in results.items()),
        key=lambda item: (-item[1], item[0]),
    )

    # If a tie crosses a VP cutoff, do not invent a league rule.
    third_score = sorted_scores[2][1]
    fourth_score = sorted_scores[3][1]
    sixth_score = sorted_scores[5][1]
    seventh_score = sorted_scores[6][1]
    if third_score == fourth_score:
        raise RuntimeError(
            f"Week {week} has a tie across the 3rd/4th scoring boundary ({third_score:.2f}); "
            "a league tie rule is required"
        )
    if sixth_score == seventh_score:
        raise RuntimeError(
            f"Week {week} has a tie across the 6th/7th scoring boundary ({sixth_score:.2f}); "
            "a league tie rule is required"
        )

    ranks = competition_ranks(sorted_scores)
    for team_id, row in results.items():
        rank = ranks[team_id]
        row["scoringRank"] = rank
        row["scoringVP"] = scoring_vp(rank)
        row["weeklyVP"] = row["matchupVP"] + row["scoringVP"]

    rows = sorted(results.values(), key=lambda row: (row["scoringRank"], -row["points"]))
    league_vp_total = sum(row["weeklyVP"] for row in rows)
    matchup_vp_total = sum(row["matchupVP"] for row in rows)
    scoring_vp_total = sum(row["scoringVP"] for row in rows)

    # For a 10-team, five-matchup week with no ties, these totals are invariants.
    if matchup_vp_total != 10:
        raise RuntimeError(f"Matchup VP total was {matchup_vp_total}; expected 10")
    if scoring_vp_total != 9:
        raise RuntimeError(f"Scoring VP total was {scoring_vp_total}; expected 9")
    if league_vp_total != 19:
        raise RuntimeError(f"League VP total was {league_vp_total}; expected 19")

    return {
        "leagueId": LEAGUE_ID,
        "season": SEASON,
        "week": week,
        "top3Cutoff": third_score,
        "top6Cutoff": sixth_score,
        "matchupVPTotal": matchup_vp_total,
        "scoringVPTotal": scoring_vp_total,
        "leagueVPTotal": league_vp_total,
        "teams": rows,
    }


def print_audit(result: dict) -> None:
    print("=" * 116)
    print(f"DA BOYS VICTORY POINTS — WEEK {result['week']} AUDIT")
    print("=" * 116)
    print(
        f"Top-3 cutoff: {result['top3Cutoff']:.2f} | "
        f"Top-6 cutoff: {result['top6Cutoff']:.2f} | "
        f"League VP awarded: {result['leagueVPTotal']}"
    )
    print("-" * 116)
    print(
        f"{'RK':>2}  {'TEAM':<31} {'PTS':>7}  {'W/L':>3}  "
        f"{'MATCH VP':>8}  {'SCORE VP':>8}  {'WEEK VP':>7}  OPPONENT"
    )
    print("-" * 116)
    for row in result["teams"]:
        print(
            f"{row['scoringRank']:>2}  {row['teamName'][:31]:<31} "
            f"{row['points']:>7.2f}  {row['result']:>3}  "
            f"{row['matchupVP']:>8}  {row['scoringVP']:>8}  {row['weeklyVP']:>7}  "
            f"{row['opponentName']} ({row['opponentPoints']:.2f})"
        )
    print("-" * 116)
    print(
        f"CHECK: matchup VP={result['matchupVPTotal']} + "
        f"scoring VP={result['scoringVPTotal']} = total VP={result['leagueVPTotal']}"
    )
    print("CALCULATION RESULT: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate weekly Da Boys Victory Points")
    parser.add_argument("--week", type=int, required=True, help="Fantasy matchup period to calculate")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also print the processed result as JSON after the audit table",
    )
    args = parser.parse_args()

    try:
        data = fetch_league()
        result = calculate_week(data, args.week)
    except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"CALCULATION RESULT: FAIL — {exc}")
        return 1

    print_audit(result)
    if args.json:
        print("\nPROCESSED JSON")
        print(json.dumps(result, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
