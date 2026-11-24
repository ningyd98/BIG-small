from scripts.graduation.g1_formal_isolation import compare_source


def test_equal_coordinates_reject_even_if_seed_and_yaw_change():
    slots = [
        {
            "reset_fixture_center_m": [0.425, 0.01, 0.035],
            "seed": 180,
            "id": "f01-dual",
            "visual_id": "g1/f01-dual",
            "group": "f01",
        }
    ]
    previous = {"seed": 78, "target": {"position": [0.425, 0.01, 0.035]}, "yaw": -0.1}
    result = compare_source(previous, slots, "g1")
    assert result["center_overlap"] == [[0.425, 0.01, 0.035]]
    assert result["seed_overlap"] == []


def test_identity_ancestors_and_reused_seeds_are_checked_independently():
    slots = [
        {
            "reset_fixture_center_m": [0.425, 0.01, 0.035],
            "seed": 180,
            "id": "f01-dual",
            "visual_id": "g1/f01-dual",
            "group": "f01",
        }
    ]
    earlier = {"ancestors": ["g1/f01-dual"], "scene": {"seed": 180}, "yaw": 0}
    result = compare_source(earlier, slots, "g1")
    assert result["identity_overlap"] == ["g1/f01-dual"]
    assert result["seed_overlap"] == [180]
    assert result["center_overlap"] == []
