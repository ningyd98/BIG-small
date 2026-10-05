"""CPU-side parsing for the frozen dual-image native candidate bridge."""
import base64
import io
import json
from PIL import Image

def parse_request(body, *, model_name):
    if body.get("model") != model_name or body.get("temperature") != 0 or body.get("max_tokens") != 512:
        raise ValueError("model/generation differs from frozen candidate")
    if body.get("response_format") != {"type": "json_object"}:
        raise ValueError("strict JSON interface required")
    messages = body.get("messages", [])
    if len(messages) != 2 or [m.get("role") for m in messages] != ["system", "user"]:
        raise ValueError("expected system and user")
    system = messages[0].get("content")
    if not isinstance(system, str) or " Schema: " not in system:
        raise ValueError("schema absent from system message")
    schema = json.loads(system.split(" Schema: ", 1)[1])
    parts = messages[1].get("content", [])
    if not isinstance(parts, list):
        raise ValueError("expected multimodal content")
    texts = [r.get("text") for r in parts if r.get("type") == "text"]
    urls = [r.get("image_url", {}).get("url") for r in parts if r.get("type") == "image_url"]
    if len(texts) != 1 or not isinstance(texts[0], str) or len(urls) != 2 or len(parts) != 3:
        raise ValueError("expected one task and two real image payloads")
    raw, images = [], []
    for url in urls:
        if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
            raise ValueError("only inline PNG accepted; external URLs prohibited")
        payload = base64.b64decode(url.split(",", 1)[1], validate=True)
        image = Image.open(io.BytesIO(payload))
        if image.format != "PNG" or image.size != (320, 240):
            raise ValueError("PNG dimensions differ from frozen320x240")
        raw.append(payload)
        images.append(image.convert("RGB"))
    if raw[0] == raw[1]:
        raise ValueError("RGB and depth unexpectedly identical")
    native = [{"role": "system", "content": system}, {"role": "user", "content": [
        {"type": "image", "image": images[0]}, {"type": "image", "image": images[1]}, {"type": "text", "text": texts[0]},
    ]}]
    return native, raw, schema
