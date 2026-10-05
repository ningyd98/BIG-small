"""Second audit, separate from paired report writer; does not rewrite source or data."""
import gzip
import hashlib
import json
from pathlib import Path
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec

ROOT = Path(__file__).resolve().parent
FROZEN_SHA = '3446acfab1c3d35869a6ff0f00cabe8c34bedb1faceaeb7ee019b31248efe4a4'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
prereg_path = ROOT / 'fresh-preregistered-assignments.json'
assert sha(prereg_path) == FROZEN_SHA
prereg = json.loads(prereg_path.read_text())
result = {'original_preregistration_sha256': FROZEN_SHA, 'original_retained_unchanged': True,
          'scope': 'EXPLORATORY_OFFLINE_TEACHER_AUDIT', 'eligible_for_formal_g1': False,
          'api_calls': 0, 'model_calls': 0, 'audited_versions': {}}
for version, dataset, development in [('workspace-baseline', 'fresh-baseline-teacher', 'baseline-t5'),
                                     ('workspace-h3', 'fresh-h3-teacher', 'variant-h3-t5')]:
    manifest = json.loads((ROOT/dataset/'manifest.json').read_text())
    dev = json.loads((ROOT/development/'manifest.json').read_text())
    frozen = prereg['versions'][version]
    assert manifest['status'] == 'COMPLETE'
    assert manifest['config'] == prereg['config']
    assert manifest['asset_sha256'] == frozen['asset_sha256']
    assert sha(ROOT/version/prereg['config']['model_path']) == frozen['asset_sha256']
    assert manifest['protocol'] == dev['protocol']
    assert manifest['protocol_hash'] == dev['protocol_hash']
    for relative, expected in manifest['protocol']['source_sha256'].items():
        assert sha(ROOT/version/relative) == expected, relative
    failures = []
    deviations = []
    per_case = []
    for execution, registration in zip(manifest['assignments'], frozen['assignments'], strict=True):
        index = execution['index']
        assert all(execution[k] == registration[k] for k in ('index','case','scene_source','seed'))
        assert execution['scene']['scene_parameters'] == registration['scene']['scene_parameters']
        derived = SceneSpec.from_parameters(registration['scene']['scene_parameters'], frozen['asset_sha256'], registration['seed'])
        assert execution['scene'] == derived.model_dump(mode='json')
        assert execution['group_id'] == derived.group_id and execution['scene_hash'] == derived.scene_hash
        compressed = (ROOT/dataset/execution['episode_path']).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == execution['sha256']
        payload = json.loads(gzip.decompress(compressed))
        assert payload['scene'] == execution['scene'] and payload['status'] == execution['status']
        metadata_changed = any(execution[k] != registration[k] for k in ('scene','group_id','scene_hash'))
        if metadata_changed:
            deviations.append(index)
        if index >= 2 and payload['status'] != 'SUCCESS':
            failures.append({'index': index, 'seed': registration['seed'], 'episode_path': execution['episode_path'],
                'sha256': execution['sha256'], 'status': payload['status'], 'reason': payload['reason'], 'outcome': payload['outcome']})
        per_case.append({'index':index,'seed':registration['seed'],'literal_matches':True,
                         'derived_identity_matches':True,'episode_sha_matches':True,'preregistered_derived_metadata_matches':not metadata_changed})
    result['audited_versions'][version] = {'manifest_sha256':sha(ROOT/dataset/'manifest.json'),
        'asset_sha256':manifest['asset_sha256'],'protocol_hash':manifest['protocol_hash'],
        'source_and_criteria_match_development':True,'all_current_source_sha_match_manifest':True,
        'cases_checked':len(per_case),'cases':per_case,'metadata_deviation_indices':deviations,
        'random_failures_retained': failures}
h3 = result['audited_versions']['workspace-h3']
baseline = result['audited_versions']['workspace-baseline']
assert h3['metadata_deviation_indices'] == list(range(2,42))
assert baseline['metadata_deviation_indices'] == []
assert [f['index'] for f in h3['random_failures_retained']] == [13,36]
assert json.loads((ROOT/'fresh-h3-teacher/manifest.json').read_text())['protocol']['criteria'] == json.loads((ROOT/'fresh-baseline-teacher/manifest.json').read_text())['protocol']['criteria']
unchanged = json.loads((ROOT/'source-scope-audit.json').read_text())['guards_controller_teacher_and_scorer_unchanged']
for path, expected in unchanged.items():
    assert sha(ROOT/'workspace-baseline'/path) == sha(ROOT/'workspace-h3'/path) == expected
result['baseline_h3_scoring_source_criteria_unchanged'] = True
result['protocol_deviation'] = '40 H3 preregistered asset-derived identity fields wrong; preserved original, independently reconstructed from original frozen literal parameters and top-level H3 SHA; execution exactly matches reconstruction.'
output = ROOT/'independent-fresh-audit.json'
output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'audit_file':str(output),'prereg_sha_unchanged':sha(prereg_path)==FROZEN_SHA,
                 'all_84_literal_and_derived_execution_identities_verified':True,
                 'baseline_h3_scoring_source_criteria_unchanged':True,'h3_failure_indices':[13,36],
                 'h3_prereg_derived_deviation_indices':h3['metadata_deviation_indices']},indent=2))
