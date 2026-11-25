import numpy as np
from scripts.graduation.g1_complete_cv_carried_surface import compare_face_patch
from scripts.graduation.g1_complete_cv_payload_observation import (
    advance_history,
    record_support,
    stable_support,
)


def test_depth_edge_and_one_pixel_pin_remain_unexplained():
    registered = np.full((3, 3), 1.25)
    color = np.full((3, 3, 3), [70, 60, 60])
    geometry = np.ones((3, 3), bool)
    assert compare_face_patch(registered, registered, color, color, geometry)
    half_foreground = registered.copy()
    half_foreground[:, 0] = 1.4
    assert not compare_face_patch(half_foreground, half_foreground, color, color, geometry)
    pin = registered.copy()
    pin[1, 1] -= 0.02
    assert not compare_face_patch(pin, registered, color, color, geometry)
    geometry[0, 0] = False
    assert not compare_face_patch(registered, registered, color, color, geometry)


def test_one_second_of_contemporary_support_has_no_duplicate_time_or_gap():
    def row(i):
        return dict(
            step=i,
            frame_id=str(i),
            center_m=[0.2, 0.25, 0.035],
            rotation=np.eye(3).tolist(),
            bottom_m=0.0,
        )

    rows = [row(i) for i in range(0, 241, 8)]
    assert stable_support(rows)
    assert not stable_support(rows[:1] * 31)
    assert not stable_support(rows[:12] + rows[13:])
    assert not stable_support(rows[:-1])
    rows[10]["center_m"][0] += 0.01
    assert not stable_support(rows)


def test_payload_clock_and_repeated_role_cannot_fill_a_missing_exposure():
    held = {"step": 104}
    history = {"recent_held": held, "support": [], "last_step": 104}
    assert advance_history(history, 112)
    assert history["recent_held"] is held
    source = {"step": 112, "frame_id": "native-origin"}
    record_support(history["support"], source)
    assert advance_history(history, 112)
    record_support(history["support"], {"step": 112, "frame_id": "same-instant-other-role"})
    assert history["support"] == [source]
    assert advance_history(history, 128)
    assert history["recent_held"] is None and history["support"] == []
    assert not advance_history(history, 120)
    assert history["last_step"] == 128
