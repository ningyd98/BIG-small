"""Actual local text, vision, OpenAI API and GPU smoke checks (no downloads)."""
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
MODEL = 'qwen3.5:4b'
IMAGE = Path.home() / 'datasets/BIGsmall/reports/vins_rgbd_small/rgb.png'

def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def command(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()

def check(client, path, request, name):
    response = client.post(path, json=request)
    save(name, dict(http_status=response.status_code, response=response.json()))
    response.raise_for_status()
    return response.json()

if __name__ == '__main__':
    results = dict(timestamp=datetime.now(timezone.utc).isoformat(), model=MODEL,
                   base_url='http://127.0.0.1:11434', downloads_during_checks=False)
    with httpx.Client(base_url=results['base_url'], trust_env=False, timeout=180) as client:
        version = client.get('/api/version')
        version.raise_for_status()
        results['ollama_version'] = version.json()['version']
        show = check(client, '/api/show', dict(model=MODEL), 'show-verification.json')
        assert 'vision' in show['capabilities']
        results['capabilities'] = show['capabilities']
        options = dict(num_ctx=8192, num_predict=256, temperature=0, seed=20261003)
        text = check(client, '/api/chat', dict(
            model=MODEL, stream=False, think=False, options=options,
            messages=[dict(role='user', content='请计算 37+58，只输出 JSON：{"sum":整数,"status":"就绪"}。')],
            format='json'), 'text-response.json')
        answer = json.loads(text['message']['content'])
        assert answer['sum'] == 95 and answer['status'] == '就绪'
        results['text_passed'] = True
        print('text passed: ' + text['message']['content'], flush=True)
        image_bytes = IMAGE.read_bytes()
        prompt = '观察图片：前景中央的长沙发是什么颜色？图片右侧前景的单人椅是什么颜色？只输出 JSON，键为 sofa_color 和 right_chair_color，值用中文。'
        vision = check(client, '/api/chat', dict(
            model=MODEL, stream=False, think=False, options=options, format='json',
            messages=[dict(role='user', content=prompt, images=[base64.b64encode(image_bytes).decode()])]),
            'vision-response.json')
        colors = json.loads(vision['message']['content'])
        assert any(x in colors['sofa_color'] for x in ['黑', '深'])
        assert '黄' in colors['right_chair_color']
        results['vision_passed'] = True
        results['vision_fixture'] = dict(path=str(IMAGE), sha256=hashlib.sha256(image_bytes).hexdigest(),
                                         prompt=prompt, expected=dict(sofa_color='黑色/深色', right_chair_color='黄色/黄绿色'),
                                         observed=colors, scope='single RGB image smoke test; not RGBD grounding or an accuracy benchmark')
        print('vision passed: ' + vision['message']['content'], flush=True)
        openai = check(client, '/v1/chat/completions', dict(
            model=MODEL, stream=False, max_tokens=128, temperature=0,
            reasoning_effort='none', messages=[dict(role='user', content='请用中文简短回复：本地服务已就绪。')]),
            'openai-response.json')
        assert openai['choices'][0]['message']['content'].strip()
        results['openai_compatible_passed'] = True
        ps = client.get('/api/ps')
        ps.raise_for_status()
        save('loaded-models.json', ps.json())
        loaded = next(m for m in ps.json()['models'] if m['name'] == MODEL)
        assert loaded['size_vram'] > 0
        results['gpu_vram_bytes'] = loaded['size_vram']
        results['model_digest'] = loaded['digest']
        results['gpu'] = command('nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version', '--format=csv,noheader')
        results['gpu_processes'] = command('nvidia-smi', '--query-compute-apps=process_name,used_memory', '--format=csv,noheader')
    results['service_active'] = command('systemctl', '--user', 'is-active', 'ollama.service')
    results['service_enabled'] = command('systemctl', '--user', 'is-enabled', 'ollama.service')
    results['login_linger'] = command('loginctl', 'show-user', 'ningyd', '-p', 'Linger')
    assert results['service_active'] == 'active' and results['service_enabled'] == 'enabled'
    results['status'] = 'LOCAL_OLLAMA_QWEN35_TEXT_VISION_ACCEPTED'
    save('acceptance.json', results)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
