"""Deterministic transport schedule with real elapsed time and finite bounds."""

import time

import pytest

from cloud_edge_robot_arm.research.clock import ExperimentClock
from cloud_edge_robot_arm.research.network import NetworkInjector, NetworkSchedule


@pytest.mark.parametrize("rtt", [100, 300, 600])
def test_request_response_delays_sum_to_rtt(rtt):
    schedule = NetworkSchedule(schedule_id="unit", rtt_ms=rtt, jitter_fraction=0,
                               loss_rate=0, bandwidth_mbit_s=10, seed=11)
    request, response = NetworkInjector(schedule).sample_delays()
    assert request + response == pytest.approx(rtt / 1000)


def test_zero_rtt_has_no_jitter():
    schedule = NetworkSchedule(schedule_id="unit", rtt_ms=0, jitter_fraction=.2,
                               loss_rate=0, bandwidth_mbit_s=10, seed=11)
    assert NetworkInjector(schedule).sample_delays() == (0, 0)


def test_seed_replays_identical_delay_schedule():
    schedule = NetworkSchedule(schedule_id="unit", rtt_ms=300, seed=11)
    left, right = NetworkInjector(schedule), NetworkInjector(schedule)
    assert [left.sample_delays() for _ in range(20)] == [right.sample_delays() for _ in range(20)]


def test_wall_time_advances_during_cloud_wait():
    elapsed_steps = []
    clock = ExperimentClock(.005, lambda n: elapsed_steps.append(n))
    time.sleep(.025)
    clock.advance_wait()
    assert clock.wall_elapsed_s() >= .025
    assert clock.sim_elapsed_s() >= .02
    assert sum(elapsed_steps) > 0
    assert clock.mapping()["wait_sim_s"] == clock.sim_elapsed_s()


def test_bandwidth_uses_bytes_in_both_directions():
    waits = []
    schedule = NetworkSchedule(schedule_id="unit", rtt_ms=100, jitter_fraction=0,
                               loss_rate=0, bandwidth_mbit_s=10, seed=11)
    injector = NetworkInjector(schedule, wait=waits.append)
    transfer = injector.begin(125000)
    injector.finish(transfer, 250000)
    assert sum(waits) == pytest.approx(.1 + .1 + .2)


def test_injected_loss_is_recorded_and_never_returns_fake_success():
    schedule = NetworkSchedule(schedule_id="unit", rtt_ms=100, loss_rate=1, seed=11)
    injector = NetworkInjector(schedule, wait=lambda _: None)
    with pytest.raises(TimeoutError):
        injector.begin(10)
    assert injector.snapshot().observed_loss_rate == 1


def test_unknown_or_nonfinite_network_values_are_rejected():
    for value in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            NetworkSchedule(schedule_id="unit", rtt_ms=value, seed=11)


def test_online_summary_uses_elapsed_roundtrip_and_never_injection_bandwidth():
    injector = NetworkInjector(NetworkSchedule(schedule_id="unit", rtt_ms=600, seed=1),
                               wait=lambda _: None)
    transfer = injector.begin(100)
    time.sleep(.015)  # stand-in for actual provider transport, not the configured RTT
    injector.finish(transfer, 200)
    observed = injector.snapshot()
    assert .01 <= observed.observed_roundtrip_s < .2
    assert observed.observed_rtt_s is None
    assert observed.observed_bandwidth_bytes_s is None


def test_response_direction_can_lose_an_already_sent_request():
    injector = NetworkInjector(NetworkSchedule(schedule_id="unit", rtt_ms=0,
                               loss_rate=.5, seed=0), wait=lambda _: None)
    transfer = injector.begin(10)
    with pytest.raises(TimeoutError, match="response"):
        injector.finish(transfer, 20)
    assert injector.snapshot().observed_loss_rate == 1
