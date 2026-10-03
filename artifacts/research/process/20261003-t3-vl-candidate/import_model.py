"""Import the pinned local Qwen3-VL files as a separate Ollama candidate.

This never pulls network content and refuses to replace any registered model.
"""

from __future__ import annotations

import json

import httpx
from download import CACHE, FILES, HERE, digest

BASE_URL = "http://127.0.0.1:11434"
MODEL = "qwen3-vl-candidate:4b-instruct"


def main() -> None:
    with httpx.Client(base_url=BASE_URL, trust_env=False, timeout=300) as client:
        version = client.get("/api/version")
        version.raise_for_status()
        if version.json().get("version") != "0.35.1":
            raise RuntimeError("unexpected Ollama version")
        tags = client.get("/api/tags")
        tags.raise_for_status()
        names = [entry.get("name") for entry in tags.json().get("models", [])]
        if MODEL in names:
            raise RuntimeError("candidate already exists; refusing to replace it")
        if "qwen3.5:4b" not in names:
            raise RuntimeError("existing qwen3.5:4b installation is unexpectedly absent")

        files: dict[str, str] = {}
        for item in FILES:
            path = CACHE / str(item["name"])
            if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                raise RuntimeError(f"source file failed pinned integrity check: {path.name}")
            sha = "sha256:" + str(item["sha256"])
            blob = client.head("/api/blobs/" + sha)
            if blob.status_code != 200:
                with path.open("rb") as stream:
                    response = client.post(
                        "/api/blobs/" + sha, content=stream,
                        headers={"Content-Length": str(item["size"])},
                    )
                response.raise_for_status()
            files[path.name] = sha
            print(f"verified local blob: {path.name}", flush=True)

        request = {
            "model": MODEL,
            "files": files,
            "stream": False,
            "parameters": {
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 20,
                "presence_penalty": 1.5,
            },
        }
        (HERE / "create-request.json").write_text(
            json.dumps(request, indent=2) + "\n", encoding="utf-8",
        )
        response = client.post("/api/create", json=request)
        (HERE / "create-response.json").write_text(
            response.text + "\n", encoding="utf-8",
        )
        response.raise_for_status()
        if response.json().get("status") != "success":
            raise RuntimeError(f"Ollama model create failed: {response.text[:300]}")

        show = client.post("/api/show", json={"model": MODEL})
        show.raise_for_status()
        (HERE / "model-show.json").write_text(
            json.dumps(show.json(), indent=2) + "\n", encoding="utf-8",
        )
        tags = client.get("/api/tags")
        tags.raise_for_status()
        entry = next(entry for entry in tags.json()["models"] if entry["name"] == MODEL)
        (HERE / "model-entry.json").write_text(
            json.dumps(entry, indent=2) + "\n", encoding="utf-8",
        )
        print(json.dumps({"model": MODEL, "digest": entry["digest"],
                          "capabilities": show.json().get("capabilities"),
                          "quantization": entry.get("details", {}).get("quantization_level")}),
              flush=True)


if __name__ == "__main__":
    main()
