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
from typing import Optional, Union, List

import numpy as np
import torch

from transformers.feature_extraction_utils import BatchFeature
from transformers.image_utils import ImageInput
from transformers.processing_utils import ImagesKwargs, MultiModalData, ProcessingKwargs, ProcessorMixin, Unpack, VideosKwargs
from transformers.tokenization_utils_base import PreTokenizedInput, TextInput
from transformers.video_utils import VideoInput


class ZDTaichu5_0_ImagesKwargs(ImagesKwargs):
    min_pixels: Optional[int]
    max_pixels: Optional[int]
    patch_size: Optional[int]
    temporal_patch_size: Optional[int]
    merge_size: Optional[int]


class ZDTaichu5_0_ProcessorKwargs(ProcessingKwargs, total=False):
    images_kwargs: ZDTaichu5_0_ImagesKwargs
    videos_kwargs: VideosKwargs
    _defaults = {
        "text_kwargs": {
            "padding": False,
        },
    }


class ZDTaichu5_0_Processor(ProcessorMixin):
    r"""
    Constructs a ZDTaichu-5.0 processor which wraps an image processor and a tokenizer into a single processor.
    [`ZDTaichu5_0_Processor`] offers all the functionalities of the image processor and tokenizer. See the
    [`~ZDTaichu5_0_Processor.__call__`] and [`~ZDTaichu5_0_Processor.decode`] for more information.
    Args:
        image_processor ([`AutoImageProcessor`], *optional*):
            The image processor is a required input.
        tokenizer ([`AutoTokenizer`], *optional*):
            The tokenizer is a required input.
        chat_template (`str`, *optional*): A Jinja template which will be used to convert lists of messages
            in a chat into a tokenizable string.
    """

    attributes = ["image_processor", "tokenizer"]

    image_processor_class = "AutoImageProcessor"
    video_processor_class = "AutoVideoProcessor"
    tokenizer_class = ("AutoTokenizer")

    def __init__(self, image_processor=None, tokenizer=None, chat_template=None, **kwargs):
        # Defaults to Qwen3's built-in vision tokens; overridden by tokenizer_config.json attributes.
        self.image_token       = getattr(tokenizer, "image_token",       "<|image_pad|>")
        self.video_token       = getattr(tokenizer, "video_token",       "<|video_pad|>")
        self.image_start_token = getattr(tokenizer, "image_start_token", "<|vision_start|>")
        self.image_end_token   = getattr(tokenizer, "image_end_token",   "<|vision_end|>")
        self.image_token_id = (
            tokenizer.image_token_id
            if getattr(tokenizer, "image_token_id", None)
            else tokenizer.convert_tokens_to_ids(self.image_token)
        )
        self.video_token_id = (
            tokenizer.video_token_id
            if getattr(tokenizer, "video_token_id", None)
            else tokenizer.convert_tokens_to_ids(self.video_token)
        )
        super().__init__(image_processor, tokenizer, chat_template=chat_template)

    def __call__(
        self,
        images: ImageInput = None,
        text: Union[TextInput, PreTokenizedInput, List[TextInput], List[PreTokenizedInput]] = None,
        videos: VideoInput = None,
        **kwargs: Unpack[ZDTaichu5_0_ProcessorKwargs],
    ) -> BatchFeature:
        """
        Main method to prepare multimodal inputs (text, images, videos) for the model. This method processes text by
        replacing image/video tokens with appropriate placeholder sequences, processes images and videos through the
        image processor, and tokenizes the final text.

        Video-as-multi-image convention
        ───────────────────────────────
        Videos are NOT processed as a separate temporal stream. Each frame is
        passed through the *image* pipeline with `max_num_tiles=1`, producing
        one 512x512 tile per frame, and the frame tile tensors are then
        APPENDED to the image stream (`pixel_values` / `num_patches` /
        `image_grid_thw`). The downstream model therefore sees a single
        uniform image batch with no separate video path.

        In the rendered prompt every frame is wrapped in
        `<|vision_start|> ... <|image_pad|> ... <|vision_end|>` — *image*
        tokens, not video tokens — and prefaced by a per-frame
        "Frame N sampled at T.TT seconds:" header. After tokenisation
        `mm_token_type_ids` therefore has no type=2 entries.

        The method performs the following key operations:
        1. Processes images using the image processor to get pixel values and patch counts
        2. Processes videos as multi-image (max_num_tiles=1) and appends frame data
           into the same pixel_values / num_patches / image_grid_thw containers
        3. Replaces `<|image_pad|>` tokens in text with `<|vision_start|>` + image tokens + `<|vision_end|>` sequences
        4. Replaces `<|video_pad|>` tokens in text with frame-by-frame descriptions including timestamps (if metadata provided)
        5. Tokenizes the processed text and combines all outputs

        Args:
            images (`PIL.Image.Image`, `np.ndarray`, `torch.Tensor`, `List[PIL.Image.Image]`, `List[np.ndarray]`, `List[torch.Tensor]`, *optional*):
                The image or batch of images to be prepared. Each image can be a PIL image, NumPy array or PyTorch
                tensor. Both channels-first and channels-last formats are supported.
            text (`str`, `List[str]`, *optional*):
                The sequence or batch of sequences to be encoded. Each sequence should be a string. The text can contain
                special tokens `<|image_pad|>` and `<|video_pad|>` that will be replaced with appropriate token sequences.
            videos (`np.ndarray`, `torch.Tensor`, `List[np.ndarray]`, `List[torch.Tensor]`, *optional*):
                The video or batch of videos to be prepared. Each video should be a 4D NumPy array or PyTorch
                tensor with shape (num_frames, channels, height, width). Both channels-first and channels-last formats
                are supported. Note: Currently only supports batch size of 1 for videos.
            images_kwargs (`Dict`, *optional*):
                Additional keyword arguments for image processing, including:
                - `min_pixels` (`int`, *optional*): Minimum number of pixels for image processing
                - `max_pixels` (`int`, *optional*): Maximum number of pixels for image processing
                - `patch_size` (`int`, *optional*): Size of patches for image processing
                - `temporal_patch_size` (`int`, *optional*): Size of temporal patches
                - `merge_size` (`int`, *optional*): Size for merging patches
            videos_kwargs (`Dict`, *optional*):
                Additional keyword arguments for video processing, including:
                - `video_metadata` (`VideoMetadata`, *optional*): Metadata containing fps information for timestamp calculation
            text_kwargs (`Dict`, *optional*):
                Additional keyword arguments for text tokenization, including:
                - `return_tensors` (`str` or [`~utils.TensorType`], *optional*): Framework for returned tensors ('tf', 'pt', 'np', 'jax')
                - `padding` (`bool`, *optional*): Whether to pad sequences (defaults to False)

        Returns:
            [`BatchFeature`]: A [`BatchFeature`] with the following fields:

            - **input_ids** -- List of token ids to be fed to a model. Returned when `text` is not `None`.
            - **attention_mask** -- List of indices specifying which tokens should be attended to by the model.
            - **pixel_values** -- Concatenated tile pixel values from BOTH real images and video frames,
              in the order they appear in `input_ids` (real images first, then video frames). Returned
              when `images` is not `None` or `videos` is not `None`.
            - **num_patches** -- List of tile counts, one entry per real image followed by one entry per
              video frame (frame entries are always 1 because max_num_tiles=1).
            - **image_grid_thw** -- LongTensor[N_images + N_frames, 3] with [1, tile_rows, tile_cols] per
              real image and [1, 1, 1] per video frame.
            - **mm_token_type_ids** -- Per-token modality classification (0=text, 1=image incl. frames).

        Raises:
            AssertionError: If videos are provided with batch size > 1 (not currently supported).

        Note:
            - Image tokens `<|image_pad|>` in text are replaced with `<|vision_start|>` + repeated image tokens + `<|vision_end|>`
            - Video tokens `<|video_pad|>` in text are replaced with frame-by-frame descriptions, each frame using `<|image_pad|>` slots
            - When video metadata with fps is provided, frame descriptions include timestamps
            - Videos are processed with max_num_tiles=1 regardless of the images setting
        """
        output_kwargs = self._merge_kwargs(
            ZDTaichu5_0_ProcessorKwargs,
            tokenizer_init_kwargs=self.tokenizer.init_kwargs,
            **kwargs,
        )
        # Initialise as independent dicts so later `**image_inputs` merging
        # is well-defined whether or not images / videos are provided.
        image_inputs: dict = {}
        image_grid_thw = None
        # Frame counts default to empty so the video-text-expansion loop is a
        # no-op when `videos` is None.
        video_num_patches: list = []

        if images is not None:
            image_inputs = self.image_processor(images=images, **output_kwargs["images_kwargs"])
            image_num_patches = image_inputs["num_patches"]
            # image_grid_thw: list of [T=1, tile_rows, tile_cols] per image
            image_grid_thw = image_inputs.pop("image_grid_thw")
            image_pixel_values = image_inputs["pixel_values"]
        else:
            image_num_patches = []

        if videos is not None:
            # ── Multi-image treatment of video ─────────────────────────────────
            # Every video frame is processed by the *image* pipeline with
            # max_num_tiles=1 so that one frame = one 512x512 tile = num_image_token
            # (e.g. 256) tokens. Frame tile tensors are then APPENDED to the
            # real-image stream:
            #
            #   pixel_values     : torch.cat([images, frames])         (total_tiles, C, H, W)
            #   num_patches      : image_num_patches + [1] * N_frames  List[int]
            #   image_grid_thw   : torch.cat([image_grids, frame_grids], dim=0)
            #
            # Order matters: text expansion below replaces image tokens
            # before video tokens, so frame slots come *after* real-image
            # slots in input_ids — these tensors must follow the same order.
            #
            # In the rendered prompt every frame is wrapped in
            #   <|vision_start|> ... <|image_pad|> x num_image_token ... <|vision_end|>
            # (image tokens, NOT video tokens) and prefaced by a per-frame
            # "Frame N sampled at T.TT seconds:" header. After tokenisation
            # mm_token_type_ids therefore has *no* type=2 entries — every
            # visual slot is type=1. The downstream model sees a single
            # uniform image stream and does not need a separate video path.
            orig_tiles = self.image_processor.max_num_tiles
            self.image_processor.max_num_tiles = 1
            try:
                frame_inputs = self.image_processor(
                    images=videos, **output_kwargs["images_kwargs"]
                )
            finally:
                self.image_processor.max_num_tiles = orig_tiles

            frame_pixel_values = frame_inputs["pixel_values"]   # (N_frames, C, H, W)
            frame_num_patches  = list(frame_inputs["num_patches"])
            frame_grid_thw     = frame_inputs["image_grid_thw"]  # (N_frames, 3) list/tensor
            video_num_patches  = frame_num_patches               # for text expansion below

            # Normalise grid containers to LongTensor so torch.cat works
            # whether the image processor returned lists or tensors.
            def _to_long_tensor(x):
                return x if isinstance(x, torch.Tensor) else torch.tensor(x, dtype=torch.long)

            if image_inputs:
                # Real images + video frames — concat along batch dim.
                image_inputs["pixel_values"] = torch.cat(
                    [image_inputs["pixel_values"], frame_pixel_values], dim=0
                )
                image_inputs["num_patches"] = (
                    list(image_inputs["num_patches"]) + frame_num_patches
                )
                image_grid_thw = torch.cat(
                    [_to_long_tensor(image_grid_thw), _to_long_tensor(frame_grid_thw)],
                    dim=0,
                )
                image_num_patches = image_inputs["num_patches"]
            else:
                # Video-only — frames become the entire image stream.
                image_inputs = {
                    "pixel_values": frame_pixel_values,
                    "num_patches": frame_num_patches,
                }
                image_grid_thw = _to_long_tensor(frame_grid_thw)
                image_num_patches = frame_num_patches

        if not isinstance(text, list):
            text = [text]
        final_image_pixel_values = []
        final_image_num_patches = []
        final_image_grid_thw = []
        text = text.copy()  # below lines change text in-place
        if images is not None:
            index = 0
            wrapped_token = self.image_start_token + self.image_token + self.image_end_token

            for i in range(len(text)):
                while self.image_token in text[i]:
                    expansion = (
                        self.image_start_token
                        + "<|placeholder|>" * image_num_patches[index] * self.image_processor.num_image_token
                        + self.image_end_token
                    )
                    # If the chat template already wrapped it, replace the whole
                    # <vision_start><image_pad><vision_end> span — avoids double wrapping.
                    # Otherwise fall back to replacing the bare <image_pad> token.
                    search = wrapped_token if wrapped_token in text[i] else self.image_token
                    text[i] = text[i].replace(search, expansion, 1)
                    index += 1
                    #final_image_pixel_values.append(image_pixel_values[index])
                    #final_image_num_patches.append(i)
                text[i] = text[i].replace("<|placeholder|>", self.image_token)
        if videos is not None:
            assert len(text) == 1, "Video is not supported for batch size > 1"
            video_metadata = output_kwargs.get("videos_kwargs", {}).get("video_metadata", None)
            i = 0
            wrapped_token = self.image_start_token + self.video_token + self.image_end_token
            if self.video_token in text[i]:
                each_frame = (
                    self.image_start_token
                    + "<|placeholder|>" * self.image_processor.num_image_token
                    + self.image_end_token
                )
                video_prompt = "This is a video:\n"
                # One iteration per frame. video_num_patches has length N_frames
                # (always 1 per frame because max_num_tiles=1 was forced above),
                # so its length is the authoritative frame count even when
                # `images` is None and `image_num_patches` is unset.
                n_frames = len(video_num_patches)
                for j in range(n_frames):
                    if video_metadata is not None and video_metadata.fps is not None:
                        timestamp = j / video_metadata.fps
                        video_prompt += f"Frame {j+1} sampled at {timestamp:.2f} seconds: {each_frame}\n"
                    else:
                        # Fallback to original format without timestamps
                        video_prompt += f"Frame {j+1}: {each_frame}\n"
                # Strip the chat-template-applied <|vision_start|>...<|vision_end|>
                # wrapping if present; otherwise replace the bare <|video_pad|>
                # token. The fallback is video_token (NOT image_token), since by
                # this point image expansion has already consumed every
                # <|image_pad|> in the prompt.
                search = wrapped_token if wrapped_token in text[i] else self.video_token
                text[i] = text[i].replace(search, video_prompt, 1)
            text[i] = text[i].replace("<|placeholder|>", self.image_token)

        return_tensors = output_kwargs["text_kwargs"].pop("return_tensors", None)
        text_inputs = self.tokenizer(text, **output_kwargs["text_kwargs"])

        # ── Build mm_token_type_ids from tokenized input_ids ─────────────
        # 0 = text, 1 = image. type=2 (video) is unreachable under the
        # multi-image-as-video convention because every frame gets expanded
        # to <|image_pad|> tokens — but we keep the video_token branch as a
        # defensive fallback for any tokenizer-injected video_pad token.
        input_ids = text_inputs["input_ids"]
        if isinstance(input_ids, list):
            mm_token_type_ids = []
            for ids in input_ids:
                tt = [0] * len(ids)
                for j, tok_id in enumerate(ids):
                    if tok_id == self.image_token_id:
                        tt[j] = 1
                    elif tok_id == self.video_token_id:
                        tt[j] = 2
                mm_token_type_ids.append(tt)
        else:
            # Already a tensor (when return_tensors is set before tokenizer call)
            mm_token_type_ids = torch.zeros_like(input_ids)
            mm_token_type_ids[input_ids == self.image_token_id] = 1
            mm_token_type_ids[input_ids == self.video_token_id] = 2

        # ── Assemble output ──────────────────────────────────────────────
        # Note: video frames have already been merged into image_inputs above,
        # so there are no separate `pixel_values_videos` / `video_grid_thw`
        # outputs. Downstream code consumes a single image stream.
        data = {**text_inputs, **image_inputs}
        data["mm_token_type_ids"] = mm_token_type_ids
        if image_grid_thw is not None:
            data["image_grid_thw"] = image_grid_thw

        return BatchFeature(data=data, tensor_type=return_tensors)

    def _get_num_multimodal_tokens(self, image_sizes=None, video_sizes=None, **kwargs):
        """
        Computes the number of placeholder tokens needed for multimodal inputs with the given sizes.
        Args:
            image_sizes (`list[list[int]]`, *optional*):
                The input sizes formatted as (height, width) per each image.
            video_sizes (`list[list[int]]`, *optional*):
                The input sizes formatted as (num_frames, height, width) per each video.
        Returns:
            `MultiModalData`: A `MultiModalData` object holding number of tokens per each of the provided
            input modalities, along with other useful data.
        """

        vision_data = {}
        if image_sizes is not None:
            images_kwargs = ZDTaichu5_0_ProcessorKwargs._defaults.get("images_kwargs", {})
            images_kwargs.update(kwargs)
            merge_size = images_kwargs.get("merge_size", None) or self.image_processor.merge_size

            num_image_patches = [
                self.image_processor.get_number_of_image_patches(*image_size, images_kwargs)
                for image_size in image_sizes
            ]
            num_image_tokens = [(num_patches // merge_size**2) for num_patches in num_image_patches]
            vision_data.update({"num_image_tokens": num_image_tokens, "num_image_patches": num_image_patches})
        return MultiModalData(**vision_data)

    def batch_decode(self, *args, **kwargs):
        """
        This method forwards all its arguments to the tokenizer's [`~PreTrainedTokenizer.batch_decode`]. Please
        refer to the docstring of this method for more information.
        """
        return self.tokenizer.batch_decode(*args, **kwargs)

    def decode(self, *args, **kwargs):
        """
        This method forwards all its arguments to the tokenizer's [`~PreTrainedTokenizer.decode`]. Please refer to
        the docstring of this method for more information.
        """
        return self.tokenizer.decode(*args, **kwargs)

    def post_process_image_text_to_text(
        self, generated_outputs, skip_special_tokens=True, clean_up_tokenization_spaces=False, **kwargs
    ):
        """
        Post-process the output of the model to decode the text.

        Args:
            generated_outputs (`torch.Tensor` or `np.ndarray`):
                The output of the model `generate` function. The output is expected to be a tensor of shape `(batch_size, sequence_length)`
                or `(sequence_length,)`.
            skip_special_tokens (`bool`, *optional*, defaults to `True`):
                Whether or not to remove special tokens in the output. Argument passed to the tokenizer's `batch_decode` method.
            clean_up_tokenization_spaces (`bool`, *optional*, defaults to `False`):
                Whether or not to clean up the tokenization spaces. Argument passed to the tokenizer's `batch_decode` method.
            **kwargs:
                Additional arguments to be passed to the tokenizer's `batch_decode method`.

        Returns:
            `list[str]`: The decoded text.
        """
        return self.tokenizer.batch_decode(
            generated_outputs,
            skip_special_tokens=skip_special_tokens,
            clean_up_tokenization_spaces=clean_up_tokenization_spaces,
            **kwargs,
        )

    @property
    def model_input_names(self):
        tokenizer_input_names = self.tokenizer.model_input_names
        image_processor_input_names = self.image_processor.model_input_names
        names_from_processor = list(dict.fromkeys(tokenizer_input_names + image_processor_input_names))
        # Note: video_grid_thw is NOT emitted under multi-image-as-video —
        # frame data lives in image_grid_thw alongside real images.
        return names_from_processor + ["mm_token_type_ids"]


    def from_messages(
        self,
        messages: list,
        return_tensors: str = "pt",
        add_vision_id: bool = True,
        **kwargs,
    ) -> BatchFeature:
        """
        Prepare model inputs directly from Qwen-style structured messages.

        This is the high-level entry point that handles the full pipeline:
        structured messages → vision loading → chat template → tokenization.

        Supports messages with typed content lists::

            messages = [
                {"role": "user", "content": [
                    {"type": "image", "image": "photo.jpg"},
                    {"type": "text", "text": "What's in this image?"},
                ]},
            ]

        Video inputs (file path, URL, or list of frame paths)::

            messages = [
                {"role": "user", "content": [
                    {"type": "video", "video": "clip.mp4", "fps": 2.0},
                    {"type": "text", "text": "Describe this video."},
                ]},
            ]

        Multi-image with automatic labelling::

            messages = [
                {"role": "user", "content": [
                    {"type": "image", "image": "a.jpg"},
                    {"type": "image", "image": "b.jpg"},
                    {"type": "text", "text": "Compare them."},
                ]},
            ]
            # With add_vision_id=True (default), the prompt includes:
            #   Picture 1: <|vision_start|><|image_pad|><|vision_end|>
            #   Picture 2: <|vision_start|><|image_pad|><|vision_end|>
            #   Compare them.

        Args:
            messages: List of message dicts with structured ``content``.
            return_tensors: Framework for returned tensors (default ``"pt"``).
            add_vision_id: If ``True`` (default), the chat template prepends
                ``Picture N:`` / ``Video N:`` labels before each vision token.
                Set to ``False`` to omit labels.
            **kwargs: Forwarded to ``self.__call__``.

        Returns:
            ``BatchFeature`` ready for ``model.generate(**inputs)``.
        """
        from .vision_utils import process_vision_info

        # 1. Load images and videos from the structured messages
        image_inputs, video_inputs, video_kwargs = process_vision_info(messages)

        # 2. Apply chat template — pass structured messages directly so the
        #    template can iterate typed content dicts, count vision elements,
        #    and emit "Picture N:" / "Video N:" labels when add_vision_id=True.
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            add_vision_id=add_vision_id,
        )

        # 3. Prepare video inputs and metadata for timestamps
        videos_kwargs = {}
        flat_videos = None
        if video_inputs is not None:
            if len(video_inputs) > 1:
                raise ValueError(
                    "Multiple videos in a single message batch are not yet "
                    "supported. Please use one video per call."
                )
            flat_videos = video_inputs[0]  # List[Image.Image]

            if video_kwargs.get("metadata_list"):
                meta = video_kwargs["metadata_list"][0]
                fps = meta.get("sample_fps") or meta.get("fps")
                if fps:
                    from transformers.video_utils import VideoMetadata
                    videos_kwargs["video_metadata"] = VideoMetadata(
                        fps=fps,
                        total_num_frames=len(flat_videos),
                    )

        return self(
            images=image_inputs,
            text=prompt,
            videos=flat_videos,
            return_tensors=return_tensors,
            videos_kwargs=videos_kwargs,
            **kwargs,
        )

    @property
    def ctx_image_token_id(self) -> int:
        return self.image_token_id


__all__ = ["ZDTaichu5_0_Processor"]