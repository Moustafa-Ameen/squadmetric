from api.team_rating import _score, grade_for_score


def test_grade_bands_include_plus_and_minus_steps() -> None:
    assert grade_for_score(100) == "A+"
    assert grade_for_score(96) == "A"
    assert grade_for_score(93) == "A-"
    assert grade_for_score(89) == "B+"
    assert grade_for_score(80) == "B-"
    assert grade_for_score(72) == "C"
    assert grade_for_score(56) == "D"
    assert grade_for_score(45) == "E"
    assert grade_for_score(44.9) == "F"


def test_relative_rating_never_claims_perfection() -> None:
    assert _score(192, 192) == 97
    assert _score(220, 192) == 97


def test_rating_makes_top_grades_difficult_to_earn() -> None:
    assert grade_for_score(_score(189.1, 192)) == "B+"
    assert grade_for_score(_score(190.6, 192)) == "A-"
