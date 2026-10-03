"""Pinned ModelScope downloads over the repository's physical-interface transport.

Run from repo root: .venv-data/bin/python artifacts/research/process/20261003-ollama-qwen35/download.py
"""
import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from cloud_edge_robot_arm.datasets.external.network import create_direct_transport

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / '.cache' / 'BIGsmall' / 'ollama-qwen35'
POLICY = dict(mode='direct', interface='enp7s0',
              dns_servers=['223.5.5.5', '223.6.6.6'],
              allowed_hosts=['modelscope.cn', 'cdn-lfs-cn-1.modelscope.cn'])
FILES = [
    dict(repo='Lixiang/ollama-release', revision='3bc525537000ecb80ffadc9fdef4566e95385181',
         name='ollama-linux-amd64.tar.zst', size=1439658961,
         sha256='9fcd79ac4575b2bd31b992eee18b1000c8ad126b451627c8f8cd091714cfbb10'),
    dict(repo='unsloth/Qwen3.5-4B-GGUF', revision='167b4afc359863325cb4164418c715421b4e9118',
         name='Qwen3.5-4B-Q4_K_M.gguf', size=2740937888,
         sha256='00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'),
    dict(repo='unsloth/Qwen3.5-4B-GGUF', revision='167b4afc359863325cb4164418c715421b4e9118',
         name='mmproj-F16.gguf', size=672423616,
         sha256='cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864'),
]

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def download(item):
    dest = CACHE / item['name']
    part = dest.with_name(dest.name + '.part')
    url = f"https://modelscope.cn/models/{item['repo']}/resolve/{item['revision']}/{item['name']}"
    if dest.exists():
        if dest.stat().st_size != item['size'] or digest(dest) != item['sha256']:
            raise RuntimeError(f'existing file integrity failure: {dest}')
        return dict(item, path=str(dest), source=url, verified=True)
    for attempt in range(1, 5):
        offset = part.stat().st_size if part.exists() else 0
        if offset == item['size']:
            break
        if offset > item['size']:
            raise RuntimeError('partial file larger than expected')
        if shutil.disk_usage(CACHE).free < item['size'] - offset + 50 * 1024**3:
            raise RuntimeError('less than 50 GiB disk reserve')
        try:
            headers = {'Accept-Encoding': 'identity', 'Range': f'bytes={offset}-'}
            with httpx.Client(transport=create_direct_transport(POLICY), trust_env=False,
                              timeout=60, follow_redirects=True) as client:
                with client.stream('GET', url, headers=headers) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        expected = f"bytes {offset}-{item['size']-1}/{item['size']}"
                        if response.headers.get('content-range') != expected:
                            raise RuntimeError('unexpected content range')
                    elif response.status_code != 200 or offset:
                        raise RuntimeError('server did not honor resume')
                    if int(response.headers.get('content-length', -1)) != item['size'] - offset:
                        raise RuntimeError('unexpected content length')
                    print(json.dumps(dict(file=item['name'], start=offset, host=response.url.host)), flush=True)
                    last = time.monotonic()
                    with part.open('ab') as output:
                        for chunk in response.iter_bytes(1024 * 1024):
                            if offset + len(chunk) > item['size']:
                                raise RuntimeError('response exceeds expected size')
                            output.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() - last >= 15:
                                print(json.dumps(dict(file=item['name'], bytes=offset, total=item['size'])), flush=True)
                                last = time.monotonic()
            if offset != item['size']:
                raise RuntimeError('incomplete response')
            break
        except (httpx.HTTPError, OSError) as exc:
            print(json.dumps(dict(file=item['name'], attempt=attempt, error=type(exc).__name__)), flush=True)
            if attempt == 4:
                raise
    actual = digest(part)
    if actual != item['sha256']:
        raise RuntimeError(f"SHA256 mismatch: {item['name']} ({actual})")
    part.rename(dest)
    print(json.dumps(dict(file=item['name'], verified_sha256=actual)), flush=True)
    return dict(item, path=str(dest), source=url, verified=True)

if __name__ == '__main__':
    CACHE.mkdir(parents=True, exist_ok=True)
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in as_completed([pool.submit(download, item) for item in FILES]):
            records.append(result.result())
            (HERE / 'downloads.json').write_text(json.dumps(dict(network_policy=POLICY, files=records), indent=2) + '\n')
