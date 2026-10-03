"""Install the hash-verified archive as a user service; no sudo or network pulls.

Run after download.py from repo root using .venv-data/bin/python.
"""
import json
import os
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import httpx
from download import CACHE, FILES, HERE, digest

VERSION = '0.35.1'
HOME_DIR = Path.home()
PREFIX = HOME_DIR / '.local' / 'opt' / 'ollama' / VERSION
MODEL_DIR = HOME_DIR / '.ollama' / 'models'
BASE_URL = 'http://127.0.0.1:11434'

def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()

def install_binary():
    archive = CACHE / FILES[0]['name']
    assert archive.stat().st_size == FILES[0]['size']
    assert digest(archive) == FILES[0]['sha256']
    PREFIX.parent.mkdir(parents=True, exist_ok=True)
    if not PREFIX.exists():
        with tempfile.TemporaryDirectory(prefix='staging-', dir=PREFIX.parent) as temp:
            with subprocess.Popen(['zstd', '-dc', str(archive)], stdout=subprocess.PIPE) as proc:
                with tarfile.open(fileobj=proc.stdout, mode='r|') as tar:
                    tar.extractall(temp, filter='data')
                assert proc.wait() == 0
            assert (Path(temp) / 'bin' / 'ollama').is_file()
            os.rename(temp, PREFIX)
    executable = PREFIX / 'bin' / 'ollama'
    link = HOME_DIR / '.local' / 'bin' / 'ollama'
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        assert link.resolve() == executable, 'refusing to replace an existing unrelated Ollama'
    else:
        link.symlink_to(executable)
    print('binary installed: ' + str(executable), flush=True)

def install_service():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    unit = HOME_DIR / '.config' / 'systemd' / 'user' / 'ollama.service'
    unit.parent.mkdir(parents=True, exist_ok=True)
    content = f'''[Unit]
Description=Ollama local model server
After=network-online.target

[Service]
Type=simple
ExecStart={PREFIX}/bin/ollama serve
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS={MODEL_DIR}"
Environment="OLLAMA_NO_CLOUD=1"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
Environment="no_proxy=localhost,127.0.0.1,::1"
UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
Restart=on-failure
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=default.target
'''
    if unit.exists():
        assert unit.read_text() == content, 'refusing to replace an existing unrelated service'
    else:
        unit.write_text(content)
    (HERE / 'ollama.service').write_text(content)
    run('systemctl', '--user', 'daemon-reload')
    run('systemctl', '--user', 'enable', '--now', 'ollama.service')
    with httpx.Client(trust_env=False, timeout=2) as client:
        for _ in range(30):
            try:
                response = client.get(BASE_URL + '/api/version')
                response.raise_for_status()
                assert response.json()['version'] == VERSION
                print('service ready: ' + response.text, flush=True)
                return
            except httpx.HTTPError:
                time.sleep(1)
    raise RuntimeError('Ollama did not become ready')

def import_model():
    with httpx.Client(base_url=BASE_URL, trust_env=False, timeout=300) as client:
        existing = client.get('/api/tags')
        existing.raise_for_status()
        names = [m['name'] for m in existing.json()['models']]
        assert 'qwen3.5:4b' not in names, 'model already registered; inspect before overwriting'
        files = {}
        for item in FILES[1:]:
            path = CACHE / item['name']
            assert path.stat().st_size == item['size'] and digest(path) == item['sha256']
            sha = 'sha256:' + item['sha256']
            if client.head('/api/blobs/' + sha).status_code != 200:
                with path.open('rb') as content:
                    response = client.post('/api/blobs/' + sha, content=content,
                                           headers={'Content-Length': str(item['size'])})
                response.raise_for_status()
            files[item['name']] = sha
            print('verified model blob: ' + item['name'], flush=True)
        request = dict(model='qwen3.5:4b', files=files, stream=False,
                       parameters=dict(temperature=1.0, top_p=0.95, top_k=20, presence_penalty=1.5))
        (HERE / 'create-request.json').write_text(json.dumps(request, indent=2) + '\n')
        response = client.post('/api/create', json=request)
        (HERE / 'create-response.json').write_text(response.text + '\n')
        response.raise_for_status()
        assert response.json().get('status') == 'success'
        response = client.post('/api/show', json={'model': 'qwen3.5:4b'})
        response.raise_for_status()
        (HERE / 'model-show.json').write_text(json.dumps(response.json(), indent=2) + '\n')
        print('model registered: qwen3.5:4b', flush=True)

if __name__ == '__main__':
    install_binary()
    install_service()
    import_model()
