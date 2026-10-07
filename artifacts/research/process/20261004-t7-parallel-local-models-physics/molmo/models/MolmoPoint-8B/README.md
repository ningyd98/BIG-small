---
license: apache-2.0
language:
- en
base_model:
- Qwen/Qwen3-8B
- google/siglip-so400m-patch14-384
pipeline_tag: image-text-to-text
tags:
- multimodal
- olmo
- molmo
- molmo2
- molmo_point
---

# MolmoPoint-8B
MolmoPoint-8B is a fully-open VLM developed by the Allen Institute for AI (Ai2) that support image, video and multi-image understanding and grounding.
It has new pointing mechansim that improves image pointing, video pointing, and video tracking, see our technical report for details.

Note the huggingface MolmoPoint model does not support training, see our github repo for the training code.

Quick links:
- 🖥️ [Demo](https://huggingface.co/spaces/allenai/MolmoPoint-8B-Demo)
- 💬 [Code](https://github.com/allenai/molmo2)
- 📂 [All Models](https://huggingface.co/collections/allenai/molmopoint)
- 📃 [Paper](https://allenai.org/papers/molmopoint)
- 📝 [Blog](https://allenai.org/blog/molmopoint)


## Quick Start

### Setup Conda Environment
```
conda create --name transformers4571 python=3.11
conda activate transformers4571
pip install transformers==4.57.1
pip install torch pillow einops torchvision accelerate decord2
```

## Inference 
We recommend running MolmoPoint with `logits_processor=model.build_logit_processor_from_inputs(model_inputs)`
to enforce points tokens are generated in a valid way.

In MolmoPoint, instead of coordinates points will be generated as a series of special
tokens, decoding the tokens back into points requires some additional
metadata from the preprocessor.
The metadata is returned by the preprocessor using the `return_pointing_metadata` flag.
Then `model.extract_image_points` and `model.extract_video_points` do the decoding, they
return a list of ({image_id|timestamps}, object_id, pixel_x, pixel_y) output points.



### Image Pointing Example:

```python
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch
import numpy as np

checkpoint_dir = "allenai/MolmoPoint-8B"  # or path to a converted HF checkpoint

model = AutoModelForImageTextToText.from_pretrained(
    checkpoint_dir,
    trust_remote_code=True,
    dtype="auto",
    device_map="auto",
)

processor = AutoProcessor.from_pretrained(
    checkpoint_dir,
    trust_remote_code=True,
    padding_side="left",
)

image_messages = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Point to the boats"},
            {"type": "image", "image": "https://assets.thesparksite.com/uploads/sites/5550/2025/01/aerial-view-of-boats-yachts-water-bike-and-woode-2023-11-27-04-51-17-utc.jpg"},
            {"type": "image", "image": "https://storage.googleapis.com/ai2-playground-molmo/promptTemplates/Stock_278013497.jpeg"},
        ]
    }
]

inputs = processor.apply_chat_template(
    image_messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True,
    padding=True,
    return_pointing_metadata=True
)
metadata = inputs.pop("metadata")
inputs = {k: v.to("cuda") for k, v in inputs.items()}

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    output = model.generate(
        **inputs,
        logits_processor=model.build_logit_processor_from_inputs(inputs),
        max_new_tokens=200
    )

generated_tokens = output[:, inputs["input_ids"].size(1):]
generated_text = processor.post_process_image_text_to_text(generated_tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)[0]
points = model.extract_image_points(
    generated_text,
    metadata["token_pooling"],
    metadata["subpatch_mapping"],
    metadata["image_sizes"]
)

# points as a list of [object_id, image_num, x, y]
# For multiple images, `image_num` is the index of the image the point is in
print(np.array(points))
```


### Video Pointing Example:
```python
video_path = "https://storage.googleapis.com/oe-training-public/demo_videos/many_penguins.mp4"
video_messages = [
    {
        "role": "user",
        "content": [
            dict(type="text", text="Point to the penguins"),
            dict(type="video", video=video_path),
        ]
    }
]

inputs = processor.apply_chat_template(
    video_messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True,
    padding=True,
    return_pointing_metadata=True
)
metadata = inputs.pop("metadata")
inputs = {k: v.to("cuda") for k, v in inputs.items()}

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    output = model.generate(
        **inputs,
        logits_processor=model.build_logit_processor_from_inputs(inputs),
        max_new_tokens=200
    )

    generated_tokens = output[:, inputs['input_ids'].size(1):]
    generated_text = processor.post_process_image_text_to_text(generated_tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False)[0]
    video_points = model.extract_video_points(
        generated_text,
        metadata["token_pooling"],
        metadata["subpatch_mapping"],
        metadata["timestamps"],
        metadata["video_size"]
    )

    # points as a list of [object_id, image_num, x, y]
    # For tracking, object_id uniquely identifies objects that might appear multiple frames.
    print(np.array(video_points))
```

## License and Use

This model is licensed under Apache 2.0. It is intended for research and educational use in accordance with Ai2’s Responsible Use Guidelines. This model is trained on third party datasets that are subject to academic and non-commercial research use only. Please review the sources to determine if this model is appropriate for your use case.