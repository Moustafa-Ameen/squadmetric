from squadmetric import model_ablation


def test_m3_variants_are_registered_directly_and_not_stacked_on_m2():
    registry = model_ablation.default_registry()
    names = {variant.name for variant in registry.values()}
    assert "baseline+xg_xa" in names
    assert "baseline+dc" in names
    assert "baseline+minutes_v2" in names
    assert "baseline+xg_xa+components" in names
    assert registry.get("baseline+xg_xa").dc_dependent is False
    assert registry.get("baseline+dc").dc_dependent is True
    assert registry.get("baseline+xg_xa+components").dc_dependent is False


def test_m3_xg_runner_selects_xg_feature_mode(monkeypatch):
    captured = {}

    def fake_runner(*args, **kwargs):
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(model_ablation, "run_season_benchmark", fake_runner)
    result = model_ablation.run_xg_xa_benchmark("players", "2024-25", "strategy")

    assert result == "result"
    assert captured["feature_mode"] == "xg_xa"
    assert captured.get("minutes_mode", "binary") == "binary"


def test_m7_component_runner_selects_component_projection(monkeypatch):
    captured = {}

    def fake_runner(*args, **kwargs):
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(model_ablation, "run_season_benchmark", fake_runner)
    result = model_ablation.run_component_benchmark("players", "2024-25", "strategy")

    assert result == "result"
    assert captured["feature_mode"] == "xg_xa"
    assert captured["projection_mode"] == "components"
