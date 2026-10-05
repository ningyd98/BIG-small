"""SOFTWARE_ONLY reader probe. No render, physics, model, or capture authority."""
import json
import tempfile
from pathlib import Path
from tests import test_native_calibration_source as fixture
from tests import test_raw_episode_v3, test_visual_owner_registration
from cloud_edge_robot_arm.vision import native_calibration as module
from cloud_edge_robot_arm.research import native_geometry_calibration as producer
from cloud_edge_robot_arm.research import raw_episode_v3

current = {
    path: fixture.digest(fixture.ROOT / path)
    for path in module.required_native_source_paths()
}
test_raw_episode_v3.SOURCES = current
test_visual_owner_registration.SOURCES = current
# Registered actual file bytes meet the arithmetic reader's path/hash join only.
# This file is not an independent UTC acquisition implementation or authority.
synthetic_independent_path = 'src/cloud_edge_robot_arm/edge/robot_adapter.py'
synthetic_independent_sources = {
    synthetic_independent_path: fixture.digest(fixture.ROOT / synthetic_independent_path)
}
outputs = []
for change in ('complete_clock', 'missing_whole_sample', 'missing_pair_hash', 'null_lower_utc'):
    with tempfile.TemporaryDirectory(prefix='source-gate-audit-', dir='/tmp') as temporary:
        root = Path(temporary)
        reg, payload = fixture.registration(root)
        envelope = raw_episode_v3.RawEpisodeEnvelopeV3.from_json(
            (root / 'case-1/envelope.json').read_text()
        )
        records = raw_episode_v3.RawEpisodeRecordsV3.from_json(
            (root / 'case-1/records.json').read_text()
        )
        raw_status = raw_episode_v3.validate_raw_episode_v3(envelope, records).status
        links = producer.original_source_reasons(
            envelope, payload, module.NativeGeometryRegistration(payload['geometry'])
        )
        clock = fixture.clock_originals(envelope, records)
        clock['independent_source_hashes'] = synthetic_independent_sources
        payload['source_hashes'].update(synthetic_independent_sources)
        if change == 'missing_whole_sample':
            clock['samples'].pop()
        elif change == 'missing_pair_hash':
            clock['samples'][0].pop('pair_hash')
        elif change == 'null_lower_utc':
            clock['samples'][0]['utc_lower_at'] = None
        clock_path = root / 'case-1/clock.json'
        clock_path.write_text(json.dumps(clock))
        payload['groups'][0]['clock_reference_path'] = 'case-1/clock.json'
        payload['original_file_hashes']['case-1/clock.json'] = fixture.digest(clock_path)
        reg = fixture.rewrite(reg, payload)
        try:
            result = producer.reconstruct_registered_calibration(reg)
            output = {
                'case': change,
                'scope': result.source_scope,
                'raw_status': raw_status,
                'source_reasons': links,
                'assigned_group_count': result.assigned_group_count,
                'independent_group_count': result.independent_group_count,
                'group_status': result.groups[0].status,
                'geometry_quantile_group_count': result.geometry_quantile.group_count,
                'geometry_bound_m': result.geometry_quantile.bound_m,
                'geometry_unavailable_groups': result.geometry_quantile.unavailable_group_ids,
                'action_bound_m': result.action_quantiles['MOVE_ABOVE'].bound_m,
                'group_reasons': result.groups[0].reasons,
            }
            if change == 'complete_clock':
                output['utc_arithmetic_uncertainty_ns'] = producer.independent_utc_uncertainty_ns(
                    clock, envelope, records
                )
        except Exception as error:
            output = {
                'case': change,
                'scope': payload['source_scope'],
                'raw_status': raw_status,
                'source_reasons': links,
                'exception_type': type(error).__name__,
                'exception': str(error),
                'assigned_group_count': 'NO_DIAGNOSTICS_RETURNED',
                'geometry_bound_m': 'NO_DIAGNOSTICS_RETURNED',
            }
        outputs.append(output)
        print(json.dumps(output, sort_keys=True))

failures = [row for row in outputs if row["assigned_group_count"] != 1]
assert not failures, ("unavailable UTC originals must retain assigned group and infinity diagnostics", failures)
