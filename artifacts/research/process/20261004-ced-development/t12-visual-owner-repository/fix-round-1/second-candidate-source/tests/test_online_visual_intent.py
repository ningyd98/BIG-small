"""Requested identity is checked against observed pixels before any motion."""

import importlib

import pytest


def validate(instruction, target=(.9, .05, .05), region=(.05, .9, .05)):
    api = importlib.import_module("cloud_edge_robot_arm.vision.online_intent")
    return api.validate_grounded_colors(instruction, target, region)


@pytest.mark.parametrize("instruction", [
    "Move the red block to the green region.",
    "将红色方块放到绿色区域",
    "pick the red cube and place it in the green target region",
])
def test_supported_instruction_is_bound_to_observed_color(instruction):
    assert validate(instruction) == ("red", "green")


@pytest.mark.parametrize("instruction", [
    "Move the blue block to the green region.",
    "Move the yellow block to the green region.",
])
def test_planner_grounded_red_pixel_cannot_replace_requested_missing_target(instruction):
    with pytest.raises(ValueError, match="requested target"):
        validate(instruction)


@pytest.mark.parametrize("instruction", [
    "Do not Move the red block to the green region.",
    "Move the red block to the green region. Move another one.",
    "Move the red block to the blue region.",
    "move something",
])
def test_unknown_negated_or_multiple_instruction_remains_unavailable(instruction):
    with pytest.raises(ValueError, match="instruction"):
        validate(instruction)


def test_red_target_green_destination_cannot_be_swapped():
    with pytest.raises(ValueError, match="destination"):
        validate("Move the red block to the green region.", region=(.9, .05, .05))


@pytest.mark.parametrize("color", ["green", "cyan"])
def test_hue_boundary_is_ambiguous_and_unavailable_for_both_identities(color):
    with pytest.raises(ValueError, match="requested target"):
        validate(f"Move the {color} block to the green region.", target=(0., 50/85, 35/85))
