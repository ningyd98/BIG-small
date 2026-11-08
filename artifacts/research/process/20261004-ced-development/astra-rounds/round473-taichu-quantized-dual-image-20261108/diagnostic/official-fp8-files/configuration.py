# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ============================================================================
#  ZDTaichu-5.0 — Top-Level Configuration
#
#  Architecture:
#    - LLM backbone: Qwen3 (pure Transformer) → Qwen3.5 (hybrid DeltaNet/Transformer)
#      · 3:1 linear-to-full attention ratio (Gated DeltaNet + full attention)
#      · Custom Qwen3_5DynamicCache for hybrid KV / recurrent states
#      · head_dim=256 (was 128), partial_rotary_factor=0.25
#      · Interleaved M-RoPE with 4D position IDs
#      · Attention output gating (sigmoid gate on q_proj)
#    - Vision encoder: C-RADIOv4-H (unchanged)
#    - Token IDs updated for Qwen3.5 vocabulary (vocab_size=248320)
#      · img_context_token_id: 151655 → 248056  (<|image_pad|>)
#      · video_context_token_id: 151656 → 248057 (<|video_pad|>)
#    - Projector output adapts to Qwen3.5 hidden_size (4096 for 9B variant)
# ============================================================================

from transformers.configuration_utils import PretrainedConfig
from transformers.utils import logging
from .cradio_config import RADIOConfig

logger = logging.get_logger(__name__)

# ---------------------------------------------------------------------------
# Import Qwen3.5 text config — requires transformers >= 5.3.0
# ---------------------------------------------------------------------------
try:
    from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig
except ImportError:
    Qwen3_5TextConfig = None
    logger.warning(
        "Could not import Qwen3_5TextConfig from transformers. "
        "Ensure transformers >= 5.3.0 is installed. "
        "Falling back to PretrainedConfig with manual attributes."
    )


# ---------------------------------------------------------------------------
# Default Qwen3.5 text configuration (9B-class variant)
# ---------------------------------------------------------------------------

_LAYER_TYPES_32 = [
    "linear_attention" if bool((i + 1) % 4) else "full_attention"
    for i in range(32)
]
# Result: [lin, lin, lin, full, lin, lin, lin, full, ... lin, lin, lin, full]
# 24 linear + 8 full attention layers


def _default_qwen3_5_text_dict() -> dict:
    """Return a dict of Qwen3.5 text config values (9B-class)."""
    return dict(
        vocab_size=248320,
        hidden_size=4096,
        intermediate_size=12288,
        num_hidden_layers=32,
        num_attention_heads=16,
        num_key_value_heads=4,
        head_dim=256,
        hidden_act="silu",
        max_position_embeddings=262144,
        rms_norm_eps=1e-6,
        use_cache=True,
        tie_word_embeddings=False,
        attention_bias=False,
        attention_dropout=0.0,
        torch_dtype="bfloat16",
        # --- Hybrid layer architecture ---
        layer_types=list(_LAYER_TYPES_32),  # copy to avoid mutation
        full_attention_interval=4,
        # --- Linear attention (Gated DeltaNet) ---
        linear_conv_kernel_dim=4,
        linear_key_head_dim=128,
        linear_value_head_dim=128,
        linear_num_key_heads=16,
        linear_num_value_heads=32,
        # --- RoPE ---
        rope_parameters={
            "rope_type": "default",
            "rope_theta": 10000000,
            "partial_rotary_factor": 0.25,
            "mrope_interleaved": True,
            "mrope_section": [11, 11, 10],
        },
    )


def _build_llm_config(cfg_dict: dict = None) -> PretrainedConfig:
    """
    Construct the LLM sub-config from a dict or defaults.

    Uses Qwen3_5TextConfig when available (transformers >= 5.3);
    otherwise falls back to a plain PretrainedConfig with the correct
    model_type so that AutoModelForCausalLM can still resolve it.
    """
    if cfg_dict is None:
        cfg_dict = _default_qwen3_5_text_dict()

    if Qwen3_5TextConfig is not None:
        return Qwen3_5TextConfig(**cfg_dict)
    else:
        config = PretrainedConfig(**cfg_dict)
        config.model_type = "qwen3_5_text"
        return config


class ZDTaichu5_0_Config(PretrainedConfig):
    """
    Configuration for ZDTaichu-5.0-9B:
        Vision encoder : C-RADIOv4-H  (ViT-H/16, 653 M params)
        LLM decoder    : Qwen3.5      (hybrid DeltaNet/Transformer)
        Projector      : RMSNorm → Linear(5120→20480) → SquaredReLU → Linear(20480→H)

    The projector input side is unchanged (C-RADIOv4-H ViT-H features at 1280,
    pixel-shuffled to 5120). Only the final projection layer adapts to the
    target LLM hidden_size (4096 for the 9B variant, vs 5120 for Qwen3-14B).

    Qwen3.5 hybrid architecture
    ----------------------------
    The text backbone alternates Gated DeltaNet (linear attention) and standard
    multi-head attention layers in a 3:1 ratio. Linear layers use a causal 1D
    convolution + gated delta rule recurrence for O(1) per-token memory during
    generation, while every 4th layer uses full quadratic attention to preserve
    global context. A custom DynamicCache handles both attention KV states and
    recurrent states.
    """

    model_type = "zdtaichu5_0"
    is_composition = True

    def __init__(
        self,
        vision_config=None,
        llm_config=None,
        force_image_size=None,
        downsample_ratio=0.5,
        template=None,
        ps_version="v2",
        image_tag_type="internvl",
        projector_hidden_size=20480,    # 4 × pixel_shuffle_dim (5120)
        vit_hidden_size=1280,           # ViT-H feature dim — same for C-RADIOv4-H
        attn_implementation="flash_attention_2",
        # Special token IDs for Qwen3.5 vocabulary (vocab_size=248320)
        img_context_token_id: int = 248056,   # <|image_pad|>
        video_context_token_id: int = 248057,  # <|video_pad|>
        **kwargs,
    ):

        # ------------------------------------------------------------------
        # Transformers 5.5.x compatibility:
        # PretrainedConfig.__init__ may call self.get_text_config()
        # during token-id validation. Therefore llm_config must exist
        # before calling super().__init__().
        # ------------------------------------------------------------------

        # ── Vision encoder ───────────────────────────────────────────────────
        if vision_config is not None:
            if isinstance(vision_config, dict):
                self.vision_config = RADIOConfig(**vision_config)
            else:
                self.vision_config = vision_config
        else:
            self.vision_config = RADIOConfig(version="c-radio_v4-h")

        # ── Language model (Qwen3.5 hybrid) ──────────────────────────────────
        if llm_config is not None:
            if isinstance(llm_config, PretrainedConfig):
                self.llm_config = llm_config
            elif isinstance(llm_config, dict):
                self.llm_config = _build_llm_config(llm_config)
            else:
                raise TypeError(
                    f"llm_config must be a dict or PretrainedConfig, got {type(llm_config)}"
                )
        else:
            self.llm_config = _build_llm_config(None)


        # Make tokenizer/generation token ids visible early.
        # Transformers 5.5.x may validate these during super().__init__().
        kwargs.setdefault("bos_token_id", getattr(self.llm_config, "bos_token_id", 248040))
        kwargs.setdefault("eos_token_id", getattr(self.llm_config, "eos_token_id", 248044))
        kwargs.setdefault("pad_token_id", getattr(self.llm_config, "pad_token_id", 248040))
        super().__init__(**kwargs)

        self.tie_word_embeddings = getattr(self.llm_config, "tie_word_embeddings", False)

        # ── VL configuration ─────────────────────────────────────────────────
        self.force_image_size = force_image_size
        self.downsample_ratio = downsample_ratio
        self.template = template
        self.ps_version = ps_version
        self.image_tag_type = image_tag_type
        self.projector_hidden_size = projector_hidden_size
        self.vit_hidden_size = vit_hidden_size

        # Special token IDs
        self.img_context_token_id = img_context_token_id
        self.video_context_token_id = video_context_token_id

        # Attention implementation propagation
        self._attn_implementation = attn_implementation
        self.vision_config.use_flash_attn = (
            self._attn_implementation is not None
            and "flash_attention" in self._attn_implementation
        )
        self.llm_config._attn_implementation = self._attn_implementation

    def get_text_config(self, decoder=False):
        # Robust fallback for Transformers 5.5.x validation.
        if hasattr(self, "llm_config"):
            return self.llm_config
        return _build_llm_config(None)

    @property
    def text_config(self):
        return self.get_text_config(decoder=True)
