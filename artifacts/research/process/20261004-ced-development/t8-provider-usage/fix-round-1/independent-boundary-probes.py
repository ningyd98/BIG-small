"""Frozen SOFTWARE_ONLY owner fixtures; no actual provider calls."""
import importlib.util
import json
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('frozen_tests', Path('tests/test_provider_usage.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
cases = [
    ('overlapping_cache_not_added', {'prompt_tokens_details': {'text_tokens': 60, 'image_tokens': 40, 'cached_tokens': 90}}, 'OBSERVED'),
    ('reasoning_already_in_text', {'completion_tokens_details': {'text_tokens': 40, 'audio_tokens': 10, 'reasoning_tokens': 30}}, 'OBSERVED'),
    ('mixed_image_video_literal_parent', {'prompt_tokens_details': {'text_tokens': 20, 'image_tokens': 40, 'video_tokens': 40}}, 'OBSERVED'),
    ('mixed_image_video_conservative_unknown', {'prompt_tokens_details': {'image_tokens': 80, 'video_tokens': 80}}, 'UNKNOWN'),
    ('error_member_null_is_unsupported', {'error': None}, 'UNKNOWN'),
]
with tempfile.TemporaryDirectory(prefix='provider-usage-fix1-probes-') as temp:
    for index, (name, modifications, expected) in enumerate(cases):
        folder = Path(temp) / str(index); folder.mkdir()
        usage = {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
        response = {'object': 'chat.completion', 'id': 'opaque-provider-id', 'model': helpers.MODEL, 'usage': usage}
        if name.startswith('error_member'): response.update(modifications)
        else: usage.update(modifications)
        registration, _ = helpers.fixture(folder, response=response)
        result = helpers.read(registration)
        row = result.attempts[0]
        print(json.dumps({'case': name, 'status': result.status, 'tokens': [row.input_tokens, row.output_tokens, row.total_tokens], 'cache': row.cached_input_tokens, 'reasoning': row.reasoning_output_tokens, 'currency': result.monetary_cost, 'billing': result.billing_status, 'scope': result.scope}))
        assert result.status == expected
        assert result.monetary_cost is None and result.billing_status == 'UNAVAILABLE'
        assert result.scope == 'ORIGINAL_PROVIDER_USAGE_METADATA'
