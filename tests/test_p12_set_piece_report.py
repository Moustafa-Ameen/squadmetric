from fpl_intelligence.p12_set_piece_report import build_set_piece_report


def test_report_surfaces_primary_penalty_taker_and_selected_transition():
    players = [
        {
            "element_id": 1,
            "name": "Primary Taker",
            "web_name": "Primary",
            "team": "TST",
            "position": "MID",
            "projections": [
                {
                    "fixtures": [
                        {
                            "set_piece_adjustment": {
                                "available": True,
                                "reason": "official_current_role_minus_official_2025_26_role",
                                "penalty_adjustment": 0.2,
                                "direct_free_kick_adjustment": 0.0,
                                "corner_adjustment": 0.0,
                                "total_adjustment": 0.2,
                                "roles": {
                                    "penalties": {
                                        "current_rank": 1,
                                        "current_share": 0.95,
                                    },
                                    "direct_free_kicks": {"current_rank": None},
                                    "corners_indirect_free_kicks": {
                                        "current_rank": None
                                    },
                                },
                            }
                        }
                    ]
                }
            ],
        }
    ]

    result = build_set_piece_report(
        players,
        {
            "season": "2026-27",
            "bootstrap_hash": "hash",
            "rules_version": "rules",
            "data_cutoff": "cutoff",
        },
        selected_ids={1},
    )

    assert result["category_coverage"]["penalties"] == 1
    assert result["primary_penalty_takers"][0]["player_name"] == "Primary Taker"
    assert result["primary_penalty_takers"][0]["selected"]
    assert result["selected_player_roles"][0]["total_adjustment_per_start"] == 0.2
    assert result["previous_role_source"]["season"] == "2025-26"
    assert len(result["previous_role_source"]["sha256"]) == 64
