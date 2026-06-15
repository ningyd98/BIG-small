from __future__ import annotations

from cloud_edge_robot_arm.experiments.profiles import NetworkProfileName, get_network_profile
from cloud_edge_robot_arm.simulation.clock import VirtualClock
from cloud_edge_robot_arm.simulation.network import NetworkMessage, NetworkSimulator


def test_virtual_clock_orders_same_time_by_priority_then_sequence() -> None:
    clock = VirtualClock()
    observed: list[str] = []

    clock.schedule(100, lambda: observed.append("late-priority"), priority=10)
    clock.schedule(100, lambda: observed.append("first-priority"), priority=1)
    clock.schedule(100, lambda: observed.append("second-priority"), priority=1)
    clock.run_until_idle()

    assert observed == ["first-priority", "second-priority", "late-priority"]
    assert clock.now_ms == 100


def test_virtual_clock_advance_executes_due_events_only() -> None:
    clock = VirtualClock()
    observed: list[str] = []

    clock.schedule(50, lambda: observed.append("due"), priority=0)
    clock.schedule(100, lambda: observed.append("future"), priority=0)
    clock.advance(50)

    assert observed == ["due"]
    assert clock.now_ms == 50


def test_network_fixed_latency_delivery_is_deterministic() -> None:
    profile = get_network_profile(NetworkProfileName.GOOD)
    first_clock = VirtualClock()
    second_clock = VirtualClock()
    first: list[tuple[int, str]] = []
    second: list[tuple[int, str]] = []

    first_network = NetworkSimulator(profile=profile, seed=123, clock=first_clock)
    second_network = NetworkSimulator(profile=profile, seed=123, clock=second_clock)
    message = NetworkMessage(message_id="m1", channel="edge-cloud", payload_size_bytes=100)

    first_network.send(message, lambda msg: first.append((first_clock.now_ms, msg.message_id)))
    second_network.send(message, lambda msg: second.append((second_clock.now_ms, msg.message_id)))
    first_clock.run_until_idle()
    second_clock.run_until_idle()

    assert first == [(20, "m1")]
    assert first == second
    assert first_network.uploaded_bytes == 100
    assert first_network.downloaded_bytes == 0


def test_network_loss_duplication_and_reordering_are_seeded() -> None:
    profile = get_network_profile(NetworkProfileName.SEVERE).model_copy(
        update={
            "loss_rate": 0.0,
            "duplication_rate": 1.0,
            "reorder_rate": 1.0,
            "base_latency_ms": 10,
            "jitter_ms": 5,
        }
    )
    clock = VirtualClock()
    delivered: list[str] = []
    network = NetworkSimulator(profile=profile, seed=5, clock=clock)

    for index in range(3):
        network.send(
            NetworkMessage(
                message_id=f"m{index}",
                channel="cloud-edge",
                payload_size_bytes=10,
            ),
            lambda msg: delivered.append(msg.message_id),
        )
    clock.run_until_idle()

    assert len(delivered) == 6
    assert sorted(delivered) == ["m0", "m0", "m1", "m1", "m2", "m2"]
    assert delivered != ["m0", "m0", "m1", "m1", "m2", "m2"]


def test_network_outage_drops_and_recovery_delivers_later_messages() -> None:
    profile = get_network_profile(NetworkProfileName.INTERMITTENT)
    clock = VirtualClock()
    delivered: list[NetworkMessage] = []
    network = NetworkSimulator(profile=profile, seed=0, clock=clock)

    network.disconnect(duration_ms=1_000)
    network.send(
        NetworkMessage(message_id="lost", channel="edge-cloud", payload_size_bytes=1),
        delivered.append,
    )
    clock.advance(1_001)
    network.send(
        NetworkMessage(message_id="ok", channel="edge-cloud", payload_size_bytes=1),
        delivered.append,
    )
    clock.run_until_idle()

    assert [message.message_id for message in delivered] == ["ok"]
    assert network.dropped_count == 1
