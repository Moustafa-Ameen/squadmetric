from fpl_intelligence.model_team_performance import build_model_team_report


def test_model_team_scorecard_never_includes_personal_team_results():
    report = build_model_team_report(
        team_id=999,
        entry={"name": "SquadMetric XI", "summary_overall_points": 90},
        history={
            "current": [
                {"event": 1, "points": 40, "overall_rank": 1000},
                {"event": 2, "points": 49, "overall_rank": 2000},
                {"event": 3, "points": 1, "overall_rank": 3000},
            ]
        },
        bootstrap={
            "events": [
                {
                    "id": 1,
                    "finished": True,
                    "data_checked": True,
                    "average_entry_score": 50,
                },
                {
                    "id": 2,
                    "finished": True,
                    "data_checked": True,
                    "average_entry_score": 55,
                },
                {
                    "id": 3,
                    "finished": False,
                    "data_checked": False,
                    "average_entry_score": 60,
                },
            ]
        },
        generated_at="2026-09-11T00:00:00Z",
    )

    assert report["team_id"] == 999
    assert report["personal_team_results_included"] is False
    assert report["all_completed_gameweeks_below_average"] is True
    assert report["total_delta_vs_official_average"] == -16
    assert [row["gameweek"] for row in report["completed_gameweeks"]] == [1, 2]
