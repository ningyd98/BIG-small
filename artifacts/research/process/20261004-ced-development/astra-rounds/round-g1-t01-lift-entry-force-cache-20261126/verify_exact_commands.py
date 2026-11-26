"""Check both readback arms with the original floating-point evaluation order."""

import argparse
from pathlib import Path

import numpy as np
from replay_entry_cache import ENTRY, HERE, OUT, witness_commands
from scripts.graduation.perception_io import pinned, read, sha, write


def exact_arm(witness, initial):
    pos, speed, accel = map(np.asarray, witness["reference"])
    gains, damping = np.asarray(witness["gains"]), np.asarray(witness["damping"])
    lower, upper = np.asarray(witness["arm_ctrl_range"]).T
    initial_state = witness["states"][0]
    sent = np.array(initial_state["qr"])
    velocity = np.zeros(7)
    previous_velocity = np.array(initial_state["dq"])
    previous_time = initial_state["time"]
    disturbance = np.array(initial)
    dt = 5 * (1 / 240)
    targets, controls = [], []
    for elapsed, state in enumerate(witness["states"][:-1]):
        mass = np.asarray(state["mass_arm"])
        current = np.asarray(state["qr"])
        dq, bias, act, passive = map(
            np.asarray, [state[k] for k in ("dq", "bias", "actuator", "passive")]
        )
        if elapsed:
            iteration_s = state["time"] - previous_time
            measured = mass @ ((dq - previous_velocity) / iteration_s) + bias - act - passive
            disturbance += min(1.0, iteration_s / 0.03) * (measured - disturbance)
            previous_velocity, previous_time = dq, state["time"]
        if elapsed % 5 == 0:
            i = elapsed // 5
            offset = (damping * speed[i] + mass @ accel[i] - disturbance) / gains
            goal = pos[i] + offset
            desired = np.clip((goal - sent) / dt, -0.5, 0.5)
            change = np.clip(desired - velocity, -(5 / 3) * dt, (5 / 3) * dt)
            velocity += change
            sent += velocity * dt
            targets.append(sent.copy())
        limited = current + np.clip(sent - current, -0.10, 0.10)
        controls.append(np.r_[np.clip(limited + bias / gains, lower, upper), state["finger_ctrl"]])
    return np.asarray(targets), np.asarray(controls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    batch = OUT / "native-prefix-01"
    seal = read(batch / "seal.json")
    witness = pinned(batch / "witness.json", seal["witness_sha256"])
    readback = read(OUT / f"{args.reader}.json")
    assert readback["witness_sha256"] == seal["witness_sha256"]
    assert witness["plan_sha256"] == sha(HERE / "plan.json")
    assert witness["source_sha256"] == sha(HERE / "replay_entry_cache.py")
    zeros, original_drive = exact_arm(witness, np.zeros(7))
    initial = witness["states"][0]
    feedback_initial = np.asarray(initial["bias"]) - initial["actuator"] - initial["passive"]
    alternate, _ = exact_arm(witness, feedback_initial)
    archived = np.asarray([s["real_arm_target"] for s in witness["states"][:-1:5]])
    archived_drive = np.asarray([s["real_ctrl"] for s in witness["states"][:-1]])
    assert np.array_equal(zeros, archived) and np.array_equal(original_drive, archived_drive)
    old_zero, old_alt = witness_commands(witness)
    assert np.allclose(zeros, old_zero, atol=1e-12, rtol=0)
    assert np.allclose(alternate, old_alt, atol=1e-12, rtol=0)
    delta = alternate - zeros
    by_tick = np.flatnonzero((abs(delta) > 1e-12).any(axis=1))
    i, j = np.unravel_index(abs(delta).argmax(), delta.shape)
    assert len(by_tick) == readback["changed_commands"]
    write(
        OUT / f"{args.reader}-exact.json",
        {
            "source_sha256": sha(Path(__file__)),
            "witness_sha256": seal["witness_sha256"],
            "original_sent_and_applied_bit_identical": True,
            "prior_reader_matches_atol_rad": 1e-12,
            "readback_sha256": sha(OUT / f"{args.reader}.json"),
            "last_changed_step": int(ENTRY + 5 * by_tick[-1]),
            "peak_changed_step": int(ENTRY + 5 * i),
            "peak_changed_joint": int(j + 1),
            "signed_peak_change_rad": float(delta[i, j]),
        },
    )


if __name__ == "__main__":
    main()
