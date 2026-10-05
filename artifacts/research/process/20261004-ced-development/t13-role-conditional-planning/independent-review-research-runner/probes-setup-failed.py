"""Independent SOFTWARE_ONLY probes against the frozen provider namespace."""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_role_conditional_planning import setup, api, PATH
from cloud_edge_robot_arm.contracts import LocalReplanningResponse
from cloud_edge_robot_arm.vision.observations import RGBDObservation

results = []


def check(name, action):
    with tempfile.TemporaryDirectory(prefix='conditional-independent-probe-') as value:
        with pytest.MonkeyPatch.context() as patch:
            action(Path(value), patch)
    results.append(name)
    print('PASS', name)


def no_paid(name, change):
    def run(directory, patch):
        provider, wire, planner, binding, data, now = setup(directory, patch)
        change(provider, binding, data, now, directory)
        with pytest.raises(api().RoleConditionalPlanningUnavailable):
            provider.plan()
        assert len(wire.requests) == len(planner.cost_ledger.requests()) == 0
    check(name, run)


no_paid('bool-owner-revision', lambda p, *_: setattr(p, 'source', replace(p.source, owner_revision=True)))
no_paid('mutated-full-fact-source-hash', lambda p, *_: p.source.online.visual_facts.update({'caller_truth': True}))
no_paid('naive-initial-clock', lambda p, b, d, n, directory: setattr(p, 'clock', lambda: n[0].replace(tzinfo=None)))
no_paid('future-calibration-domain', lambda p, *_: setattr(p, 'source', replace(p.source, online=replace(p.source.online, observation=p.source.online.observation.model_copy(update={'calibration_version': None})))))


def source_file_alias(p, binding, data, now, directory):
    source = binding.root / PATH
    backup = directory / 'identical-provider.py'
    backup.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(backup)
no_paid('identical-source-file-symlink', source_file_alias)


def before_ttl(directory, patch):
    provider, wire, planner, _, _, now = setup(directory, patch)
    clock = iter((now[0], now[0] + timedelta(seconds=6)))
    provider.clock = lambda: next(clock)
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert len(wire.requests) == len(planner.cost_ledger.requests()) == 0
check('deadline-crossing-during-image-preparation', before_ttl)


def final_ttl(directory, patch):
    provider, wire, planner, _, _, now = setup(directory, patch)
    clock = iter((now[0], now[0], now[0], now[0] + timedelta(seconds=6)))
    provider.clock = lambda: next(clock)
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert len(wire.requests) == len(planner.cost_ledger.requests()) == 1
check('deadline-crossing-before-final-builder', final_ttl)


for field in ('ActionEvidence', 'stage', 'authenticated_owner', 'permission', 'executable_contract'):
    def run(directory, patch, field=field):
        provider, wire, planner, *_ = setup(directory, patch, change=lambda d: d.update({field: {'status':'VALID'}}))
        with pytest.raises(api().RoleConditionalPlanningUnavailable):
            provider.plan()
        assert len(wire.requests) == len(planner.cost_ledger.requests()) == 1
        assert planner.cost_ledger.requests()[0].monetary_cost is None
    check('reject-inner-authority-' + field, run)


def nested_duplicate(directory, patch):
    def change(decision):
        value = json.dumps(decision)
        return value.replace('"target_pixel": [1, 1]', '"target_pixel": [0, 0], "target_pixel": [1, 1]', 1)
    provider, wire, planner, *_ = setup(directory, patch, change=change)
    with pytest.raises(api().RoleConditionalPlanningUnavailable):
        provider.plan()
    assert len(wire.requests) == len(planner.cost_ledger.requests()) == 1
check('duplicate-inner-nested-pixel-key', nested_duplicate)


for point, system in (((1001,0),'normalized_1000'), ((-1,0),'pixel'), ((10**200,0),'pixel')):
    def run(directory, patch, point=point, system=system):
        def change(decision):
            decision['replacements'][0]['target_pixel'] = list(point)
        provider, wire, planner, *_ = setup(directory, patch, change=change, coordinate_system=system)
        with pytest.raises(api().RoleConditionalPlanningUnavailable):
            provider.plan()
        assert len(wire.requests) == len(planner.cost_ledger.requests()) == 1
    check('coordinate-reject-' + system + '-' + str(point[0])[:12], run)


def repeated_frames(directory, patch):
    provider, wire, planner, _, data, now = setup(directory, patch)
    original_requirements = [r.digest() for r in provider.source.original.requirements.values()]
    for index in range(3):
        if index:
            now[0] += timedelta(seconds=.5)
            source = provider.source
            frame = source.online.observation.model_dump()
            frame.update(frame_id=f'independent-frame-{index}', observation_id='', checksum_sha256='',
                         captured_at=now[0], sim_time_s=source.online.observation.sim_time_s+.5)
            provider.source = replace(source, online=replace(source.online, observation=RGBDObservation.model_validate(frame)))
        result = provider.plan()
        assert result.replacements[1].current_preconditions[0][1] == 'FAIL'
        assert [r.digest() for r in provider.source.original.requirements.values()] == original_requirements
        assert result.scope == 'PLANNING_ONLY'
        assert result.execution_admitted is result.method_admitted is False
        for field in ('steps', 'activation_token', 'stage', 'action_evidence', 'permission'):
            assert not hasattr(result, field)
        with pytest.raises(ValueError):
            LocalReplanningResponse.model_validate(result.to_payload())
        assert result.valid_until <= data['original'].effective_deadline_at
    assert len(wire.requests) == 3
    assert all(row.monetary_cost is None for row in planner.cost_ledger.requests())
check('three-current-frames-retain-future-FAIL-no-execution-or-money', repeated_frames)


def source_binding_only(directory, patch):
    provider, wire, _, *_ = setup(directory, patch)
    provider.source = replace(provider.source, source_scope='SOURCE_BINDING_ONLY')
    result = provider.plan()
    assert result.scope == 'PLANNING_ONLY'
    assert result.execution_admitted is result.method_admitted is False
    assert len(wire.requests) == 1
check('source-binding-metadata-never-owner-authority', source_binding_only)

print(json.dumps({'probe_count':len(results),'passed':results,'scope':'SOFTWARE_ONLY','actual_provider_renderer_controller_calls':0},indent=2))
