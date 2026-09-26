from gridlock.georesolution.resolver import _candidates


def test_candidate_matching_is_case_insensitive_and_rejects_weak_names() -> None:
    features = [
        {"id": "way/1", "properties": {"power": "substation", "name": "Jasper Substation"}, "geometry": {"type": "Point", "coordinates": [-81, 32]}},
        {"id": "way/2", "properties": {"power": "substation", "name": "Different Place"}, "geometry": {"type": "Point", "coordinates": [-82, 33]}},
    ]

    assert [candidate.feature_id for candidate in _candidates("jasper", features)] == ["way/1"]
    assert _candidates("unknown", features) == []


def test_explicit_wrong_operator_is_vetoed() -> None:
    features = [
        {"id": "way/1", "properties": {"power": "substation", "name": "Jasper Substation", "operator": "Duke Energy"}, "geometry": {"type": "Point", "coordinates": [-81, 32]}},
        {"id": "way/2", "properties": {"power": "substation", "name": "Jasper Substation"}, "geometry": {"type": "Point", "coordinates": [-81, 32]}},
    ]

    assert [candidate.feature_id for candidate in _candidates("Jasper", features, ("Dominion Energy South Carolina",))] == ["way/2"]
