"""Build sanitized season data for the Da Boys Victory Points dashboard.

The ESPN league is private, but this repository is public. This processor only
writes fantasy-football fields needed by the dashboard. It intentionally does
NOT persist ESPN members, account IDs, cookies, or the full private API response.

Outputs:
- data/raw/week-XX.json       sanitized matchup snapshots for finalized weeks
- data/processed/2026.json   dashboard-ready season dataset
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from calculate_victory_points import (
    EXPECTED_MATCHUPS,
    EXPECTED_TEAMS,
    LEAGUE_ID,
    SEASON,
    calculate_week,
    fetch_league,
    team_display_name,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def is_finalized_week(data: dict, week: int) -> bool:
    """A week is finalized only when all five ESPN matchups have a winner."""
    matchups = [
        m
        for m in (data.get("schedule") or [])
        if isinstance(m, dict) and m.get("matchupPeriodId") == week
    ]
    if len(matchups) != EXPECTED_MATCHUPS:
        return False

    seen: set[int] = set()
    for matchup in matchups:
        if matchup.get("winner") not in {"HOME", "AWAY"}:
            return False
        for side_name in ("home", "away"):
            side = matchup.get(side_name) or {}
            team_id = side.get("teamId")
            points = side.get("totalPoints")
            if not isinstance(team_id, int) or not isinstance(points, (int, float)):
                return False
            if team_id in seen:
                return False
            seen.add(team_id)

    return len(seen) == EXPECTED_TEAMS


def regular_season_weeks(data: dict) -> list[int]:
    """Infer regular-season matchup periods from ESPN's returned schedule."""
    weeks = sorted(
        {
            int(m["matchupPeriodId"])
            for m in (data.get("schedule") or [])
            if isinstance(m, dict) and isinstance(m.get("matchupPeriodId"), int)
        }
    )
    return weeks


def contiguous_finalized_weeks(data: dict) -> list[int]:
    """Process only the completed sequence from Week 1 onward."""
    completed: list[int] = []
    for week in regular_season_weeks(data):
        if week != len(completed) + 1:
            break
        if not is_finalized_week(data, week):
            break
        completed.append(week)
    return completed


def competition_rank(values: list[tuple[int, float]]) -> dict[int, int]:
    """Standard competition rank for descending values."""
    ranks: dict[int, int] = {}
    previous_value: float | None = None
    previous_rank = 0
    for position, (team_id, value) in enumerate(values, start=1):
        if previous_value is None or value != previous_value:
            previous_rank = position
            previous_value = value
        ranks[team_id] = previous_rank
    return ranks


def sanitized_week_snapshot(data: dict, week: int) -> dict:
    teams = data.get("teams") or []
    team_by_id = {
        int(team["id"]): team
        for team in teams
        if isinstance(team, dict) and isinstance(team.get("id"), int)
    }

    matchups = [
        m
        for m in (data.get("schedule") or [])
        if isinstance(m, dict) and m.get("matchupPeriodId") == week
    ]

    safe_matchups = []
    for matchup in matchups:
        home = matchup.get("home") or {}
        away = matchup.get("away") or {}
        home_id = home.get("teamId")
        away_id = away.get("teamId")
        safe_matchups.append(
            {
                "week": week,
                "winner": matchup.get("winner"),
                "home": {
                    "teamId": home_id,
                    "teamName": team_display_name(team_by_id.get(home_id, {})),
                    "points": float(home.get("totalPoints", 0.0)),
                },
                "away": {
                    "teamId": away_id,
                    "teamName": team_display_name(team_by_id.get(away_id, {})),
                    "points": float(away.get("totalPoints", 0.0)),
                },
            }
        )

    return {
        "leagueId": LEAGUE_ID,
        "season": SEASON,
        "week": week,
        "finalized": True,
        "matchups": safe_matchups,
    }


def build_season(data: dict) -> dict:
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

    schedule_weeks = regular_season_weeks(data)
    finalized_weeks = contiguous_finalized_weeks(data)
    if not finalized_weeks:
        raise RuntimeError("No finalized fantasy weeks are available yet")

    aggregates: dict[int, dict] = {}
    for team_id, team in team_by_id.items():
        aggregates[team_id] = {
            "teamId": team_id,
            "teamName": team_display_name(team),
            "abbrev": team.get("abbrev"),
            "logo": team.get("logo"),
            "wins": 0,
            "losses": 0,
            "pointsFor": 0.0,
            "pointsAgainst": 0.0,
            "matchupVP": 0,
            "scoringVP": 0,
            "totalVP": 0,
            "fourVPWeeks": 0,
            "zeroVPWeeks": 0,
            "scoringRankSum": 0,
            "weeklyVP": [],
            "weeklyScores": [],
        }

    weeks: list[dict] = []
    rank_history: dict[int, list[dict]] = {team_id: [] for team_id in team_by_id}

    for week in finalized_weeks:
        result = calculate_week(data, week)
        week_result = deepcopy(result)

        for row in week_result["teams"]:
            agg = aggregates[row["teamId"]]
            if row["result"] == "W":
                agg["wins"] += 1
            else:
                agg["losses"] += 1
            agg["pointsFor"] += row["points"]
            agg["pointsAgainst"] += row["opponentPoints"]
            agg["matchupVP"] += row["matchupVP"]
            agg["scoringVP"] += row["scoringVP"]
            agg["totalVP"] += row["weeklyVP"]
            agg["fourVPWeeks"] += int(row["weeklyVP"] == 4)
            agg["zeroVPWeeks"] += int(row["weeklyVP"] == 0)
            agg["scoringRankSum"] += row["scoringRank"]
            agg["weeklyVP"].append(row["weeklyVP"])
            agg["weeklyScores"].append(row["points"])
            row["cumulativeVP"] = agg["totalVP"]

        vp_order = sorted(
            ((team_id, agg["totalVP"]) for team_id, agg in aggregates.items()),
            key=lambda x: (-x[1], x[0]),
        )
        week_vp_ranks = competition_rank(vp_order)
        for row in week_result["teams"]:
            row["cumulativeVPRank"] = week_vp_ranks[row["teamId"]]
            rank_history[row["teamId"]].append(
                {
                    "week": week,
                    "vp": row["cumulativeVP"],
                    "vpRank": row["cumulativeVPRank"],
                }
            )

        weeks.append(week_result)

    vp_values = sorted(
        ((team_id, agg["totalVP"]) for team_id, agg in aggregates.items()),
        key=lambda x: (-x[1], x[0]),
    )
    pf_values = sorted(
        ((team_id, round(agg["pointsFor"], 2)) for team_id, agg in aggregates.items()),
        key=lambda x: (-x[1], x[0]),
    )
    vp_ranks = competition_rank(vp_values)
    pf_ranks = competition_rank(pf_values)

    standings = []
    games_played = len(finalized_weeks)
    for team_id, agg in aggregates.items():
        average_scoring_rank = agg["scoringRankSum"] / games_played
        average_weekly_vp = agg["totalVP"] / games_played
        previous_rank = (
            rank_history[team_id][-2]["vpRank"]
            if len(rank_history[team_id]) >= 2
            else None
        )
        current_rank = vp_ranks[team_id]
        rank_change = None if previous_rank is None else previous_rank - current_rank

        standings.append(
            {
                "teamId": team_id,
                "teamName": agg["teamName"],
                "abbrev": agg["abbrev"],
                "logo": agg["logo"],
                "vpRank": current_rank,
                "vpRankChange": rank_change,
                "totalVP": agg["totalVP"],
                "record": f"{agg['wins']}-{agg['losses']}",
                "wins": agg["wins"],
                "losses": agg["losses"],
                "pointsFor": round(agg["pointsFor"], 2),
                "pointsAgainst": round(agg["pointsAgainst"], 2),
                "pointsForRank": pf_ranks[team_id],
                "matchupVP": agg["matchupVP"],
                "scoringVP": agg["scoringVP"],
                "fourVPWeeks": agg["fourVPWeeks"],
                "zeroVPWeeks": agg["zeroVPWeeks"],
                "averageScoringRank": round(average_scoring_rank, 2),
                "averageWeeklyVP": round(average_weekly_vp, 2),
                "weeklyVP": agg["weeklyVP"],
                "weeklyScores": agg["weeklyScores"],
                "rankHistory": rank_history[team_id],
            }
        )

    # VP is the only official primary ordering currently encoded. Points For is
    # used only to make tied rows deterministic until the league's standings
    # tiebreak policy is specified.
    standings.sort(key=lambda row: (-row["totalVP"], -row["pointsFor"], row["teamId"]))

    status = data.get("status") or {}
    next_week = finalized_weeks[-1] + 1
    if schedule_weeks and next_week > schedule_weeks[-1]:
        next_week = None

    return {
        "league": {
            "leagueId": LEAGUE_ID,
            "season": SEASON,
            "teamCount": len(team_by_id),
            "regularSeasonWeeks": len(schedule_weeks),
        },
        "rules": {
            "matchupWinVP": 2,
            "scoringVP": {
                "ranks1to3": 2,
                "ranks4to6": 1,
                "ranks7to10": 0,
            },
            "weeklyMaximumVP": 4,
            "weeklyMinimumVP": 0,
        },
        "sync": {
            "syncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "espnCurrentMatchupPeriod": status.get("currentMatchupPeriod"),
            "espnLatestScoringPeriod": status.get("latestScoringPeriod"),
            "finalizedThroughWeek": finalized_weeks[-1],
            "nextUnfinalizedWeek": next_week,
        },
        "standingsNote": (
            "VP rank uses Victory Points only. Points For is used only as a deterministic "
            "display order when VP totals are tied; no official standings tiebreaker has "
            "been encoded yet."
        ),
        "standings": standings,
        "weeks": weeks,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_summary(season: dict) -> None:
    print("=" * 88)
    print("DA BOYS SEASON PROCESSOR")
    print("=" * 88)
    print(f"League: {season['league']['leagueId']} | Season: {season['league']['season']}")
    print(
        f"Finalized through Week {season['sync']['finalizedThroughWeek']} | "
        f"Next unfinalized: {season['sync']['nextUnfinalizedWeek']}"
    )
    print("-" * 88)
    print(f"{'VP RK':>5}  {'TEAM':<31} {'VP':>3}  {'REC':>5}  {'PF':>8}  {'PF RK':>5}")
    print("-" * 88)
    for row in season["standings"]:
        print(
            f"{row['vpRank']:>5}  {row['teamName'][:31]:<31} "
            f"{row['totalVP']:>3}  {row['record']:>5}  "
            f"{row['pointsFor']:>8.2f}  {row['pointsForRank']:>5}"
        )
    print("-" * 88)
    print("SEASON PROCESSING RESULT: PASS")


def main() -> int:
    data = fetch_league()
    season = build_season(data)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    finalized_through = season["sync"]["finalizedThroughWeek"]
    for week in range(1, finalized_through + 1):
        write_json(RAW_DIR / f"week-{week:02d}.json", sanitized_week_snapshot(data, week))

    write_json(PROCESSED_DIR / f"{SEASON}.json", season)
    print_summary(season)
    print(f"Wrote: data/processed/{SEASON}.json")
    print(f"Wrote sanitized snapshots: data/raw/week-01.json .. week-{finalized_through:02d}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
