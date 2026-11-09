"""Research glue around the unchanged, pinned Xiaomi-Lens-0 public API."""

import hashlib
import json
from pathlib import Path


def native_prompt(phrase):
    return (f'Locate all instances in the image that match the description "{phrase}". '
            'Report bbox coordinates and masks. If no matching instance is visible, return None.')


def build_inputs(processor, image, prompt, device):
    # Official infer.py's processor path, with the checkpoint's documented
    # enable_thinking switch made explicit before any model inference.
    messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    processor.tokenizer.padding_side = "left"
    inputs = processor(text=[text], images=[image], return_tensors="pt", padding=True, add_special_tokens=False)
    return inputs.to(device), text


def tensor_evidence(inputs):
    import torch
    result = {}
    for key, value in inputs.items():
        if not isinstance(value, torch.Tensor):
            continue
        raw = value.detach().contiguous().reshape(-1).view(torch.uint8).cpu().numpy().tobytes()
        result[key] = {"shape": list(value.shape), "dtype": str(value.dtype), "bytes": len(raw),
                       "sha256": hashlib.sha256(raw).hexdigest()}
        if key == "image_grid_thw":
            result[key]["values"] = value.tolist()
    return result


def build_json_inputs(processor, image, system, instruction, device):
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": instruction}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    processor.tokenizer.padding_side = "left"
    inputs = processor(text=[text], images=[image], return_tensors="pt", padding=True, add_special_tokens=False)
    return inputs.to(device), text


def verify_public_case(root, row):
    path = root / row["rgb_path"]
    if path.stat().st_size != row["rgb_bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != row["rgb_sha256"]:
        raise ValueError("public RGB bytes changed")
    return path


def strip_native_end_tokens(text):
    return text.split("<|im_end|>", 1)[0].split("<|endoftext|>", 1)[0].strip()


def normalize_lens(infer, raw_text, raw_masks, width, height):
    from score_native import box_pixel, mask_pixel

    answer, thought_masks = infer.split_answer_content(raw_text)
    body = strip_native_end_tokens(answer)
    boxes = infer.parse_answer_bboxes(raw_text)
    absence = body.lower() in ("", "none", "none.", "null", "[]", "<bbox>none</bbox>")
    if not boxes:
        status = "REFUSAL" if absence and raw_masks is None else "INVALID"
        return {"box": {"status": status, "predictions": [], "point": None},
                "mask": {"status": status, "predictions": [], "point": None}, "thought_masks": thought_masks}
    box_predictions = []
    for box in boxes:
        mapped, point = box_pixel(box, width, height, "normalized_1000")
        box_predictions.append({"box": list(mapped), "point": list(point)})
    result = {"box": {"status": "DETECTED", "predictions": box_predictions, "point": box_predictions[0]["point"]},
              "mask": {"status": "INVALID", "predictions": [], "point": None}, "thought_masks": thought_masks}
    if raw_masks is None:
        return result
    masks = raw_masks[0, thought_masks:]
    if len(masks) != len(boxes):
        result["mask"]["error"] = "final mask count differs from final box count"
        return result
    predictions = []
    for mask in masks:
        binary, point = mask_pixel(mask.float().cpu().tolist(), width, height, kind="logit", threshold=0)
        predictions.append({"point": None if point is None else list(point), "foreground_pixels": sum(sum(row) for row in binary)})
    result["mask"] = {"status": "DETECTED" if predictions[0]["point"] is not None else "REFUSAL",
                      "predictions": predictions, "point": predictions[0]["point"]}
    return result
