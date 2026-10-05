"""Temporary direct HTTPS experiment transport. Secret exists only in memory."""
import concurrent.futures
import getpass
import hashlib
import json
import pathlib
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from cloud_edge_robot_arm.datasets.external.network import DirectNetworkBackend, create_direct_transport

BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ROOT = pathlib.Path('/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-qwen-cloud-comparison')
ROOT.mkdir(parents=True, exist_ok=True)

def save(path, value):
    path = pathlib.Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('output outside experiment directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')

host = urlsplit(BASE).hostname
policy = {'mode': 'direct', 'interface': 'enp7s0',
          'dns_servers': ['223.5.5.5', '223.6.6.6'], 'allowed_hosts': [host]}
addresses = DirectNetworkBackend(policy)._resolve(host)
routes = []
for address in addresses:
    try:
        p = subprocess.run(['ip', '-j', 'route', 'get', address, 'oif', 'enp7s0'], capture_output=True, text=True, check=True)
        routes.extend(json.loads(p.stdout))
    except Exception as exc:
        routes.append({'error_type': type(exc).__name__})
save(ROOT/'network-direct-token-plan.json', {'endpoint': BASE, 'resolved_addresses': addresses, 'routes': routes, 'policy': policy,
    'trust_env': False, 'follow_redirects': False, 'tls_verification': True,
    'created_at': datetime.now(timezone.utc).isoformat()})
print('NETWORK', json.dumps({'addresses': addresses, 'devices': [r.get('dev') for r in routes]}), flush=True)
key = getpass.getpass('API key (no echo, memory only): ')
if not key or '\n' in key:
    raise ValueError('invalid credential')
client = httpx.Client(transport=create_direct_transport(policy), trust_env=False, follow_redirects=False, timeout=httpx.Timeout(90, connect=15),
                      headers={'Authorization': 'Bearer '+key}, verify=True)

def redact(value):
    return re.sub(r'sk-[A-Za-z0-9_.-]+', '[REDACTED]', value.replace(key, '[REDACTED]'))

def call(item):
    started = time.perf_counter()
    body = json.loads(pathlib.Path(item['body']).read_text()) if item.get('body') else None
    record = {'label': item['label'], 'started_at': datetime.now(timezone.utc).isoformat(),
              'method': 'POST' if body else 'GET', 'trust_env': False,
              'request_sha256': hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() if body else None}
    try:
        with client.stream('POST' if body else 'GET', BASE+('/chat/completions' if body else '/models'), json=body) as response:
            stream = response.extensions.get('network_stream')
            sock = stream.get_extra_info('socket') if stream else None
            record['network'] = {'bound_interface': sock.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 256).rstrip(b'\0').decode() if sock else None,
                                 'peer': sock.getpeername() if sock else None, 'local': sock.getsockname() if sock else None}
            if record['network']['bound_interface'] != 'enp7s0':
                raise RuntimeError('physical interface verification failed')
            record['http_status'] = response.status_code
            record['response_headers'] = {k: v for k,v in response.headers.items()
                                          if k.lower() in {'x-request-id','request-id','content-type','date'}}
            chunks = bytearray()
            for chunk in response.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 2_000_000:
                    raise ValueError('response exceeds size limit')
            raw = redact(chunks.decode('utf8'))
        try:
            record['response'] = json.loads(raw)
        except ValueError:
            record['error'] = {'type': 'NonJSONResponse', 'message': raw[:400]}
        record['ok'] = response.status_code == 200 and 'response' in record
    except Exception as exc:
        record['ok'] = False
        record['error'] = {'type': type(exc).__name__, 'message': redact(str(exc))[:400]}
    record['latency_ms'] = round((time.perf_counter()-started)*1000, 3)
    save(item['output'], record)
    decoded = record.get('response', {})
    print(json.dumps({'label': item['label'], 'status': record.get('http_status'),
        'ok': record['ok'], 'latency_ms': record['latency_ms'],
        'model': decoded.get('model'), 'usage': decoded.get('usage'),
        'error': decoded.get('error', record.get('error'))}, ensure_ascii=False), flush=True)
    return record

models = call({'label': 'model_catalog_token_plan', 'output': str(ROOT/'model-catalog-token-plan.json')})
if models.get('http_status') in (401,403):
    print('AUTHENTICATION_OR_PERMISSION_BLOCKED; no inference calls made', flush=True)
    client.close()
    sys.exit(2)
ids = [m.get('id') for m in models.get('response', {}).get('data', []) if isinstance(m,dict)]
print('CANDIDATE_IDS', json.dumps([x for x in ids if x and ('qwen3.8' in x or 'qwen3-vl' in x)]), flush=True)
print('READY_JSON_COMMANDS', flush=True)
count = 0
for line in sys.stdin:
    command = json.loads(line)
    if command.get('op') == 'exit':
        break
    if command.get('op') != 'batch':
        raise ValueError('unsupported operation')
    requests = command['requests']
    if count + len(requests) > 100:
        raise ValueError('experiment request limit reached')
    for item in requests:
        path = pathlib.Path(item['body']).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('input outside experiment directory')
        body = json.loads(path.read_text())
        if body.get('max_tokens', 0) > 2048 or body.get('stream', False):
            raise ValueError('invalid output budget')
        if not body.get('model','').startswith('qwen'):
            raise ValueError('non-Qwen request')
    count += len(requests)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(call, requests))
    print('BATCH_DONE', count, flush=True)
client.close()
print('CLOSED', flush=True)
