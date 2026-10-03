"""Seeded static scene proposals; only SceneSpec defines dataset scene identity."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec

COLORS = {"red": [.9, .12, .08, 1.], "blue": [.08, .2, .9, 1.],
          "yellow": [.95, .8, .06, 1.]}


def sample_scene(config: DatasetConfig, seed: int) -> SceneSpec:
    rng = np.random.default_rng(seed)
    destination = {"position": [.20, .25, .002], "half_size": [.07, .07, .002],
                   "rgba": [.1, .6, .2, 1.]}
    placed: list[dict[str, Any]] = [destination]
    color = str(rng.choice(list(COLORS)))

    def object_spec(target: bool) -> dict[str, Any]:
        size = rng.uniform(*config.half_size, size=3)
        for _ in range(300):
            x = float(rng.uniform(*(config.target_x if target else (.13, .65))))
            y = float(rng.uniform(*(config.target_y if target else (-.30, .32))))
            if not (-.28 < x - size[0] and x + size[0] < .98 and
                    -.43 < y - size[1] and y + size[1] < .43):
                continue
            if all(abs(x - obj["position"][0]) > size[0] + obj["half_size"][0] + .015 or
                   abs(y - obj["position"][1]) > size[1] + obj["half_size"][1] + .015
                   for obj in placed):
                break
        else:
            raise ValueError("scene layout cannot fit non-overlapping objects within the table")
        name = color if target else str(rng.choice([c for c in COLORS if c != color]))
        obj = {"position": [x, y, float(size[2] + .008)], "half_size": size.tolist(),
               "rgba": COLORS[name].copy(), "color_name": name,
               "mass_kg": float(rng.uniform(.05, .15)),
               "friction": float(rng.uniform(.5, 1.0))}
        placed.append(obj)
        return obj

    params = {"target": object_spec(True),
              "distractors": [object_spec(False) for _ in range(
                  int(rng.integers(config.distractor_count[0], config.distractor_count[1] + 1)))],
              "destination": destination,
              "camera": {"position": [float(rng.uniform(*config.camera_x)),
                                      float(rng.uniform(*config.camera_y)),
                                      float(rng.uniform(*config.camera_height))],
                         "quaternion": [1., 0., 0., 0.],
                         "fovy": float(rng.uniform(*config.camera_fovy))},
              "light_intensity": float(rng.uniform(*config.light_intensity)),
              "depth_noise_m": float(rng.choice(config.depth_noise_m)),
              "invalid_depth_fraction": float(rng.choice(config.invalid_depth_fractions))}
    asset_hash = hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest()
    return SceneSpec.from_parameters(params, asset_hash, seed)
