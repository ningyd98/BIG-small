"""Current repository defaults; historical snapshots keep their explicit identities."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VISUAL_MODEL = "qwen3-vl-candidate:4b-instruct"
DEFAULT_MODEL_CONFIG = REPOSITORY_ROOT / "configs/research/model_qwen3vl_4b_gripper_v2.yaml"
DEFAULT_FROZEN_DIR = (
    REPOSITORY_ROOT / "artifacts/research/process/20261004-gripper-project-migration/model-probe"
)
