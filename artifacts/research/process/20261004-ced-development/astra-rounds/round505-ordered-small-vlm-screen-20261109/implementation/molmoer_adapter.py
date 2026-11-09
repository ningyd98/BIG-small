"""Native Molmo2-ER single RGB pointing, with explicit published 0..1000 units."""
import hashlib
import re
from pathlib import Path
from score_native import point_pixel


def next_call_index(started, authorized):
    if not 0 <= started < authorized <= 134:
        raise ValueError("candidate generation budget exhausted or invalid")
    return started + 1


def native_prompt(phrase):
    return f'Point to the {phrase}. If the requested item is not visible, return exactly ABSENT and no points.'


def messages(case, root, *, dual=False):
    from PIL import Image
    path = Path(root) / case["rgb_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case["rgb_sha256"]
    content = [{"type": "text", "text": native_prompt(case["phrase"])},
               {"type": "image", "image": Image.open(path).convert("RGB")}]
    if dual:
        depth = Path(root) / case["depth_path"]
        assert hashlib.sha256(depth.read_bytes()).hexdigest() == case["depth_sha256"]
        content.append({"type": "image", "image": Image.open(depth).convert("RGB")})
    return [{"role": "user", "content": content}]


def build_inputs(processor, case, root, *, dual=False):
    conversation = messages(case, root, dual=dual)
    rendered = processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
    features = processor.apply_chat_template(conversation, tokenize=True, add_generation_prompt=True,
                                             return_tensors="pt", return_dict=True, padding=True)
    return features, rendered


def tensor_evidence(features):
    import torch
    result = {}
    for key, value in features.items():
        if isinstance(value, torch.Tensor):
            tensor = value.detach().cpu().contiguous()
            result[key] = {"shape": list(tensor.shape), "dtype": str(tensor.dtype),
                           "sha256": hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest()}
    return result


def strip_end(raw):
    text = raw
    for terminal in ("<|im_end|>", "<|endoftext|>"):
        if text.endswith(terminal):
            text = text[:-len(terminal)]
    return text


def parse_native(raw, width, height):
    text = strip_end(raw).strip()
    result = {"status": "INVALID", "point": None, "predictions": []}
    if text == "ABSENT":
        result["status"] = "REFUSAL"
        return {"point": result}
    tags = list(re.finditer(r'<points\b[^>]*\bcoords="([^"]*)"[^>]*>', text))
    try:
        if not tags or re.search(r"\bABSENT\b", text):
            raise ValueError("missing native point tag or contradictory absence")
        predictions = []
        for tag in tags:
            for group in re.split(r"[\t:;,]", tag.group(1)):
                fields = group.strip().split()
                if not fields or any(not re.fullmatch(r"\d+", part) for part in fields):
                    raise ValueError("malformed image/point coordinate group")
                values = list(map(int, fields))
                if len(values) < 4 or (len(values) - 1) % 3 or values[0] != 1:
                    raise ValueError("unexpected image index or point arity")
                for i in range(1, len(values), 3):
                    coords = values[i+1:i+3]
                    point = point_pixel(coords, width, height, "normalized_1000")
                    predictions.append({"object_id": values[i], "normalized_1000": coords, "point": list(point)})
        result.update(status="DETECTED", point=predictions[0]["point"], predictions=predictions)
    except (ValueError, IndexError) as error:
        result["error"] = str(error)
    return {"point": result}
