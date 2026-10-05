"""Build paired, registered RGB and depth images for visual planning."""

from __future__ import annotations

import base64
import io
import json

from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation

_DEFAULT_IMAGE_SIZE = (640, 640)
VISUAL_PROMPT_VERSION = "rgbd.direct-grounding.v2"


def display_image_size(
    observation: RGBDObservation, *, image_size: tuple[int, int] | None = None
) -> tuple[int, int]:
    """Return the transmitted image dimensions within a width/height bound.

    Both images use this same size; images smaller than the bound are never enlarged.
    """
    bounds = _DEFAULT_IMAGE_SIZE if image_size is None else image_size
    if (
        not isinstance(bounds, tuple)
        or len(bounds) != 2
        or any(type(value) is not int or value <= 0 for value in bounds)
    ):
        raise ValueError("image_size must be a pair of positive integer bounds")
    max_width, max_height = bounds
    width, height = observation.width, observation.height
    if width <= max_width and height <= max_height:
        return width, height
    if width * max_height >= height * max_width:
        return max_width, max(1, height * max_width // width)
    return max(1, width * max_height // height), max_height


def display_to_observation_pixel(
    pixel: tuple[int, int],
    observation: RGBDObservation,
    *,
    image_size: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Map a transmitted image pixel center to the registered metric-depth pixel."""
    displayed_width, displayed_height = display_image_size(observation, image_size=image_size)
    if (
        not isinstance(pixel, (tuple, list))
        or len(pixel) != 2
        or any(type(value) is not int for value in pixel)
    ):
        raise ValueError("selected pixel must contain two integers")
    u, v = pixel
    if not (0 <= u < displayed_width and 0 <= v < displayed_height):
        raise ValueError("selected pixel is outside transmitted image")
    return (
        (2 * u + 1) * observation.width // (2 * displayed_width),
        (2 * v + 1) * observation.height // (2 * displayed_height),
    )


def model_to_observation_pixel(
    pixel: tuple[int, int],
    observation: RGBDObservation,
    *,
    image_size: tuple[int, int] | None = None,
    coordinate_system: str = "pixel",
) -> tuple[int, int]:
    """Decode an explicit wire convention; never infer units from a point's values."""
    if coordinate_system == "pixel":
        return display_to_observation_pixel(pixel, observation, image_size=image_size)
    if coordinate_system != "normalized_1000":
        raise ValueError("unsupported coordinate system")
    display_image_size(observation, image_size=image_size)
    if (
        not isinstance(pixel, (tuple, list))
        or len(pixel) != 2
        or any(type(value) is not int for value in pixel)
    ):
        raise ValueError("selected normalized point must contain two integers")
    if any(not 0 <= value <= 1000 for value in pixel):
        raise ValueError("selected normalized point is outside [0, 1000]")
    return (
        min(observation.width - 1, pixel[0] * observation.width // 1000),
        min(observation.height - 1, pixel[1] * observation.height // 1000),
    )


def _resized_png_base64(value: str, size: tuple[int, int]) -> str:
    with Image.open(io.BytesIO(base64.b64decode(value, validate=True))) as image:
        if image.size == size:
            return value
        output = io.BytesIO()
        image.resize(size, resample=Image.Resampling.NEAREST).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def build_visual_messages(
    instruction: str,
    observation: RGBDObservation,
    *,
    image_size: tuple[int, int] | None = None,
    coordinate_system: str = "pixel",
    decision_schema: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Create directly serializable Ollama messages with two aligned images.

    A compatible API may convert each `images` entry to an `image_url` content
    part. No frame identifier, oracle sidecar or raw metric depth enters the prompt.
    """
    displayed_size = display_image_size(observation, image_size=image_size)
    if coordinate_system not in {"pixel", "normalized_1000"}:
        raise ValueError("unsupported coordinate system")
    rgb = _resized_png_base64(observation.rgb_png_base64, displayed_size)
    depth = _resized_png_base64(observation.depth_png_base64(), displayed_size)
    units = (
        "[x,y] normalized integer coordinates 0 to 1000 (top-left 0,0, bottom-right 1000,1000)"
        if coordinate_system == "normalized_1000"
        else "[u,v] integer pixels in the TRANSMITTED image, "
        "u increasing right and v increasing down"
    )
    system = (
        "Inspect image 1 (RGB) to identify the requested object and destination. "
        "Image 2 is aligned depth for spatial context. Return only JSON. "
        f"target_pixel and destination_pixel are {units}. "
        "Select the visible object top center and destination interior. "
        "If uncertain use null points, skills [], reported_confidence 0. "
        "For a visible pick-and-place task skills must be exactly "
        '["HOME","MOVE_ABOVE","APPROACH","GRASP","LIFT","MOVE_TO_REGION",'
        '"PLACE","RELEASE","RETREAT","HOME"]. '
        "target_label describes the object. reported_confidence is your uncertainty estimate."
    )
    if decision_schema is not None:
        system += " Schema: " + json.dumps(decision_schema)
    user = instruction
    if coordinate_system == "pixel":
        near, far = observation.depth_range()
        user += (
            f"\nTransmitted image size: {displayed_size[0]}x{displayed_size[1]}; "
            f"original registered RGB-D size: {observation.width}x{observation.height}. "
            "Return pixel coordinates in the transmitted image only. Both images use identical "
            "pixel coordinates. Depth is optical-axis metres: "
            f"grayscale 255={near:.6f}m near, 1={far:.6f}m far, 0=invalid; linear mapping. "
            "When near equals far, all valid depth pixels are 1."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user, "images": [rgb, depth]},
    ]
