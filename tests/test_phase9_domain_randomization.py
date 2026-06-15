from __future__ import annotations

from cloud_edge_robot_arm.simulation.config import RandomizationLevel
from cloud_edge_robot_arm.simulation.randomization.sampler import DomainRandomizationPolicy


def test_phase9_domain_randomization_is_seed_reproducible() -> None:
    policy = DomainRandomizationPolicy.default(RandomizationLevel.MODERATE)

    assert policy.sample(seed=42) == policy.sample(seed=42)
    assert policy.sample(seed=42) != policy.sample(seed=43)


def test_phase9_randomization_manifest_contains_units_and_sources() -> None:
    sample = DomainRandomizationPolicy.default(RandomizationLevel.SEVERE).sample(seed=9)

    assert sample.version
    assert sample.parameters["object_mass_kg"].unit == "kg"
    assert (
        sample.parameters["friction_coefficient"].source
        == "configs/phase9/domain_randomization.yaml"
    )
    assert sample.parameters["camera_depth_noise_m"].value >= 0
