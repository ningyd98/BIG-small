"""Owner-rebound SOFTWARE_ONLY fixtures; no remote/billing authority."""
import importlib.util
import json
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('frozen_usage_fixtures', Path('tests/test_provider_usage.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
results = []

def record(name, reg):
    result = helpers.read(reg)
    value = {'case': name, 'status': result.status, 'reasons': result.reasons,
             'original_attempts': result.original_attempts, 'sent_attempts': result.sent_attempts,
             'tokens': [a.total_tokens for a in result.attempts],
             'currency': result.monetary_cost, 'billing_status': result.billing_status,
             'scope': result.scope}
    results.append(value)
    print(json.dumps(value))

with tempfile.TemporaryDirectory(prefix='provider-usage-review-cases-') as directory:
    base = Path(directory)
    for index, object_type in enumerate((None, 'error', 'response', 'chat.completion.chunk', 'chat.completion')):
        folder = base / str(index); folder.mkdir()
        payload = {'id': 'opaque-provider-id', 'model': helpers.MODEL,
                   'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}
        if object_type is not None: payload['object'] = object_type
        if object_type == 'error': payload['error'] = {'message': 'synthetic failed response'}
        reg, _ = helpers.fixture(folder, response=payload, status='ERROR' if object_type == 'error' else 'SUCCESS')
        record('response_object_' + str(object_type), reg)
    for index, kind in enumerate(('empty_ledger', 'all_unsent'), start=5):
        folder = base / str(index); folder.mkdir()
        reg, evidence = helpers.fixture(folder)
        rows = json.loads((evidence / 'ledger.json').read_text())
        if kind == 'empty_ledger': rows = []
        else: rows[0].update(sent_at=None, status='ERROR', serialized_sent_bytes=0, serialized_received_bytes=0)
        (evidence / 'ledger.json').write_text(json.dumps(rows))
        (evidence / 'wire.json').write_text('[]')
        (evidence / 'request.json').unlink(); (evidence / 'response.json').unlink()
        record(kind, helpers.rebound(reg, evidence))
    for index, details in enumerate(({'text_tokens': 70, 'image_tokens': 70}, {'text_tokens': 40, 'audio_tokens': 40}), start=7):
        folder = base / str(index); folder.mkdir()
        usage = {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
        usage['prompt_tokens_details' if index == 7 else 'completion_tokens_details'] = details
        payload = {'id': 'opaque-provider-id', 'model': helpers.MODEL, 'object': 'chat.completion', 'usage': usage}
        reg, _ = helpers.fixture(folder, response=payload)
        record('disjoint_modalities_exceed_' + ('input' if index == 7 else 'output'), reg)

assert all(row['currency'] is None and row['billing_status'] == 'UNAVAILABLE' for row in results)
assert next(row for row in results if row['case'] == 'response_object_chat.completion.chunk')['status'] == 'UNKNOWN'
assert next(row for row in results if row['case'] == 'response_object_chat.completion')['status'] == 'OBSERVED'
