"""Predeclared R505 research messages. No oracle or model-answer repair."""
import hashlib
import re
from pathlib import Path
from score_native import point_pixel, box_pixel
from molmoer_adapter import tensor_evidence, strip_end, next_call_index


def native_prompt(mode, phrase):
    if mode == "box":
        return (f'Locate the {phrase}.\nGenerate coordinates for one object bounding box. Constraints: x1,y1,x2,y2 in [0,1000]. '
                'Response must be in the format: <object> (x1, y1), (x2, y2) </object>. '
                'If the requested item is not visible, return exactly ABSENT.')
    return (f'Point to the {phrase}.\nExpress the coordinates as a tuple sequence in the format <area> (x1, y1), (x2, y2), ... </area> '
            'with all coordinate values normalized to the standardized pixel coordinate system spanning 0 to 1000. '
            'If the requested item is not visible, return exactly ABSENT.')


def build(processor, request, root, processor_kwargs):
    from PIL import Image
    content = []
    for role in ("rgb", "depth"):
        if role + "_path" not in request:
            continue
        path = Path(root) / request[role + "_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == request[role + "_sha256"]
        content.append({"type": "image", "image": Image.open(path).convert("RGB")})
    if request["stage"] == "NATIVE_RGB":
        prompt = native_prompt(request["mode"], request["phrase"])
        messages = [{"role": "user", "content": content + [{"type": "text", "text": prompt}]}]
    else:
        messages = [{"role": "system", "content": request["system"]},
                    {"role": "user", "content": content + [{"type": "text", "text": request["instruction"]}]}]
    rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                             enable_thinking=False)
    features = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                             enable_thinking=False, return_dict=True, return_tensors="pt", **processor_kwargs)
    return features, rendered


def parse_rynn(raw, mode, width, height):
    text = strip_end(raw).strip()
    result = {"status": "INVALID", "point": None, "predictions": []}
    if text == "ABSENT":
        result["status"] = "REFUSAL"
        return {mode: result}
    wrapper = "object" if mode == "box" else "area"
    match = re.fullmatch(rf"<{wrapper}>\s*(.*?)\s*</{wrapper}>", text, re.S)
    try:
        if not match:
            raise ValueError("missing exact native wrapper")
        body = match.group(1)
        pairs = re.findall(r"\((\d+),\s*(\d+)\)", body)
        residue = re.sub(r"\(\d+,\s*\d+\)", "", body).replace(",", "").strip()
        if residue or not pairs or (mode == "box" and len(pairs) != 2):
            raise ValueError("malformed native tuple sequence")
        values = [list(map(int, p)) for p in pairs]
        if mode == "box":
            box, point = box_pixel(values[0] + values[1], width, height, "normalized_1000")
            predictions = [{"box": list(box), "point": list(point)}]
        else:
            predictions = [{"point": list(point_pixel(p, width, height, "normalized_1000")), "normalized_1000": p} for p in values]
        result.update(status="DETECTED", point=predictions[0]["point"], predictions=predictions)
    except (ValueError, IndexError) as error:
        result["error"] = str(error)
    return {mode: result}
