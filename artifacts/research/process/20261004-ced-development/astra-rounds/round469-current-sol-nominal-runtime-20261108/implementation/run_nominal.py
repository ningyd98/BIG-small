"""R469 one-shot fresh Sol nominal probe; secret input is local hidden TTY only."""

import argparse
import base64
import csv
import ctypes
import fcntl
import getpass
import hashlib
import importlib.metadata
import io
import json
import math
import os
import resource
import select
import shutil
import signal
import subprocess
import sys
import time
import warnings
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parents[1]
HERE = ROUND / 'implementation'
RAW = ROOT / 'cache/research/r469-current-sol-nominal-20261108'
CONFIG = ROOT / 'configs/research/ced_roles.yaml'
PLAN_SHA = '67982b44cc9c1fd9758f53d78d7ffc19d38fbaa6cd3ffd25a49a746f4ceb586f'
PLAN = json.loads((ROUND / 'plan.json').read_bytes())
SUPPLEMENT = ROUND.parent / 'round475-sol-supervisor-owned-process-closure-20261108'
SUPPLEMENT_HASHES = {
    'plan.md': 'b21ddb773bf17feff2cd2b588cdfd56e09422c5d3e4af4154c9870ebecfe450a',
    'plan.json': '46571001d53b23fd993ad966c98e5524e0a79e2cec519880fddbcbdb696ac496',
    'intake/input-manifest.json': 'eca369a23cebee5c123fb72c19717763ff5b66f389009e9ac082558990dac6bf',
}
SUPERVISION = None


class OuterDeadline(Exception):
    pass


def deadline_check():
    state = SUPERVISION
    if state is not None and time.monotonic() >= state['outer_deadline']:
        state['outer_hit'] = True
        if state['phase'] in ('SCAN', 'SEAL'):
            raise OuterDeadline()


def sha(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            deadline_check()
            block = stream.read(65536)
            if not block:
                break
            checksum.update(block)
    deadline_check()
    return checksum.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value, *, exempt=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        for part in json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False).iterencode(value):
            if not exempt:
                deadline_check()
            stream.write(part)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    if not exempt:
        deadline_check()


def event(name, **values):
    with (RAW / 'runtime-events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'event': name, 'utc': datetime.now(UTC).isoformat(),
                                 'monotonic': time.monotonic(), **values}, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def size(root):
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob('*'):
        deadline_check()
        if path.is_symlink():
            raise ValueError('symlink in owned output')
        if path.is_file():
            total += path.stat().st_size
    return total


def pins():
    deadline_check()
    assert sha(ROUND / 'plan.json') == PLAN_SHA
    for row in PLAN['inputs'] + json.loads((ROUND / 'source-pins.json').read_bytes()):
        deadline_check()
        path = ROOT / row['path']
        assert path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], row['path']
    for name, checksum in SUPPLEMENT_HASHES.items():
        assert sha(SUPPLEMENT / name) == checksum
    for row in json.loads((SUPPLEMENT / 'intake/input-manifest.json').read_bytes()):
        path = ROOT / row['path']
        if path == Path(__file__).resolve():
            path = SUPPLEMENT / 'intake/run_nominal.before.py'
        assert path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']


def checkpoint(started, planner=None, settings=None):
    pins()
    assert time.monotonic() - started < 900
    assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 4294967296
    assert size(RAW) <= 1073741824 and shutil.disk_usage(ROOT).free >= 2147483648
    if planner is not None:
        from cloud_edge_robot_arm.vision.role_models import cloud_request_settings
        assert cloud_request_settings(planner) == settings


def bindings(metadata, config, key=''):
    from scripts import probe_rgbd_roles as probe
    from cloud_edge_robot_arm.model_control.models import ModelProviderProfile
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.vision.role_models import (
        RoleModelBundle, RoleProviderSnapshot, cloud_request_settings,
        configuration_hash, resolve_cloud_role,
    )
    profile = ModelProviderProfile(**metadata)
    store = InMemorySecretStore()
    if key:
        store.set_secret(profile.profile_id, key)
    profile = profile.model_copy(update={'secret_present': store.has_secret(profile.profile_id)})

    def selected(profile_id):
        assert profile_id == profile.profile_id
        return profile

    service = SimpleNamespace(get_profile=selected, secret_store=store)
    planner, cloud = resolve_cloud_role(
        service, profile.profile_id, source_hashes=probe.source_fingerprints(),
        allow_paid=True, image_size=(320, 240), coordinate_system='normalized_1000',
        grasp_profile='mujoco_upright_box_v2', available_model_ids=[],
        expected_model_family='gpt-6.1-sol')
    edge_config = config['edge']
    edge = RoleProviderSnapshot(role='EDGE', provider_id=edge_config['provider_id'],
        provider_location=edge_config['provider_location'], model_id=None, revision=None,
        weight_digest=None, quantization=None,
        request_config_hash=configuration_hash(edge_config['policy']),
        source_hashes=probe._hash_sources(edge_config['source_paths']))
    device = probe._hash_sources(config['device']['source_paths'])
    bundle = RoleModelBundle(cloud, edge.provider_id, edge.digest(), configuration_hash(device))
    return SimpleNamespace(profile=profile, store=store, planner=planner, cloud=cloud,
        edge=edge, device=device, bundle=bundle, settings=cloud_request_settings(planner))


def new_report(config):
    return {'schema_version': 'ced.role-probe.v1', 'status': 'NOT_STARTED',
        'source': None, 'transport': None, 'capture': {'synchronized': False}, 'attempts': [],
        'started_at': datetime.now(UTC).isoformat(), 'finished_at': None,
        'probe_config': config['probe'], 'config_sha256': None,
        'config_path': str(HERE / 'frozen-role-config.json'), 'bundle': None,
        'bundle_hash': None, 'edge_snapshot': None, 'edge_policy': config['edge']['policy'],
        'device_source_hashes': None, 'request_settings': None, 'final_request_settings': None,
        'acceptance_scope': 'nominal cloud RGB-D planning probe only', 'scope': 'NOMINAL_PROBE_ONLY',
        'physical_acceptance': False, 'edge_acceptance': False, 'dispatch': False,
        'billing_cost': None, 'pure_inference_duration_s': None, 'planned_attempt_count': 4,
        'unexecuted_attempt_count': 4}


def preflight():
    assert not (HERE / 'preflight.json').exists()
    pins()
    assert not RAW.exists()
    assert shutil.disk_usage(ROOT).free >= 2147483648
    started = time.monotonic()

    def timeout(signum, frame):
        raise TimeoutError('CPU preflight wall limit')

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(60)

    def no_network(event_name, args):
        if event_name.startswith('socket.') or event_name in ('subprocess.Popen', 'os.fork', 'os.system'):
            raise RuntimeError('network/process action forbidden during CPU preflight')

    sys.addaudithook(no_network)
    from scripts import probe_rgbd_roles as probe
    from cloud_edge_robot_arm.model_control.models import ModelProviderProfile
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.model_resolver import compatible_chat_generation, validate_sol_route
    from cloud_edge_robot_arm.vision.planner import VisualDecision

    config = probe.read_role_config(CONFIG)
    assert config['cloud']['model_family'] == 'gpt-6.1-sol'
    assert config['cloud']['grasp_profile'] == 'mujoco_upright_box_v2'
    assert config['probe'] == {'scenario_id': 'S01_NORMAL_STATIC', 'seed': 0,
        'instruction': PLAN['scene']['instruction'], 'warm_runs': 3}
    metadata = {key: value for key, value in PLAN['profile_metadata'].items()
                if key in ModelProviderProfile.model_fields}
    metadata.update(display_name='Sol R469 frozen read-only session view', secret_present=False)
    profile = ModelProviderProfile(**metadata)
    metadata = profile.model_dump(mode='json')
    assert metadata['api_key'] is None and metadata['max_retries'] == 0
    validate_sol_route('openai_compatible', profile.model_name,
                       profile.base_url, profile.chat_completions_path)
    config['cloud']['profile_id'] = profile.profile_id
    binding = bindings(metadata, config)
    assert set(PLAN['report_contract']['preserve_from_run_probe']) <= set(new_report(config))
    assert not binding.store.has_secret(profile.profile_id)
    settings = binding.settings
    assert settings['generation_parameters'] == {'reasoning_effort': 'low', 'max_completion_tokens': 4096}
    assert settings['timeout_s'] == 180 and settings['model'] == 'gpt-6.1-sol'
    fields = compatible_chat_generation(settings['model'], settings['generation_parameters'])
    assert fields == PLAN['request_contract']['generation']
    assert set(fields) | {'model', 'messages', 'response_format'} == {
        'model', 'messages', 'response_format', 'reasoning_effort', 'max_completion_tokens'}
    assert VisualDecision.model_json_schema()['type'] == 'object'
    assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
    assert hasattr(os, 'wait4') and hasattr(signal, 'setitimer')
    simulator = SimulatorConfig(camera_width=320, camera_height=240, render_rgb=True,
        render_depth=True, domain_randomization=False, seed=0, model_path=PLAN['scene']['model_path'])
    assert simulator.model_path == 'assets/robots/franka_panda/scene.xml'
    assert sha(ROOT / simulator.model_path) == PLAN['scene']['sha256']
    assert ET.fromstring((ROOT / simulator.model_path).read_bytes()).find('./worldbody/camera') is not None
    versions = {name: importlib.metadata.version(name) for name in
                ('numpy', 'Pillow', 'mujoco', 'pydantic', 'PyYAML')}
    save(HERE / 'frozen-role-config.json', config)
    save(HERE / 'profile-metadata.json', metadata)
    generation = {'plan_sha256': PLAN_SHA, 'runner_sha256': sha(Path(__file__)),
        'source_manifest_sha256': sha(ROUND / 'source-pins.json'),
        'config_sha256': sha(CONFIG), 'frozen_config_sha256': sha(HERE / 'frozen-role-config.json'),
        'profile_metadata_sha256': sha(HERE / 'profile-metadata.json'),
        'source_context_sha256': sha(HERE / 'source-context.json'),
        'supplemental_plans': {str((SUPPLEMENT / name).relative_to(ROOT)): checksum
                              for name, checksum in SUPPLEMENT_HASHES.items() if name.startswith('plan.')},
        'supplemental_input_manifest_sha256': SUPPLEMENT_HASHES['intake/input-manifest.json'],
        'before_runner_sha256': sha(SUPPLEMENT / 'intake/run_nominal.before.py'),
        'python': sys.version, 'dependency_versions': versions,
        'production_cloud_sources': probe.source_fingerprints()}
    save(HERE / 'source-generation.json', {'generation': generation, 'digest': digest(generation)})
    files = {name: sha(HERE / name) for name in ('frozen-role-config.json', 'profile-metadata.json',
                                              'source-generation.json', 'source-context.json')}
    result = {'status': 'READY_WAITING_HIDDEN_TTY_SECRET', 'runner_sha256': sha(Path(__file__)),
        'plan_sha256': PLAN_SHA, 'files': files, 'request_settings': settings,
        'bundle': binding.bundle.evidence(), 'bundle_hash': binding.bundle.digest(),
        'edge_snapshot': binding.edge.evidence(), 'device_source_hashes': binding.device,
        'profile_secret_present': False, 'source_generation': digest(generation),
        'elapsed_s': time.monotonic() - started,
        'peak_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        'counters': {'API': 0, 'physics': 0, 'render': 0, 'secret_reads': 0,
                     'backend_constructions': 0, 'model_loads': 0}}
    assert result['elapsed_s'] <= 60 and result['peak_RSS_bytes'] <= 4294967296
    pins()
    save(HERE / 'preflight.json', result)
    signal.alarm(0)
    print(json.dumps({'status': result['status'], 'source_generation': result['source_generation'],
                      'counters': result['counters']}), flush=True)


def ready():
    pins()
    receipt = json.loads((HERE / 'preflight.json').read_bytes())
    assert receipt['status'] == 'READY_WAITING_HIDDEN_TTY_SECRET'
    assert receipt['runner_sha256'] == sha(Path(__file__)) and receipt['plan_sha256'] == PLAN_SHA
    for name, checksum in receipt['files'].items():
        assert sha(HERE / name) == checksum
    generation = json.loads((HERE / 'source-generation.json').read_bytes())['generation']
    assert generation['python'] == sys.version
    assert all(importlib.metadata.version(name) == version
               for name, version in generation['dependency_versions'].items())
    return receipt


def expected_body(request, frame, settings):
    from PIL import Image
    from cloud_edge_robot_arm.vision.messages import build_visual_messages
    from cloud_edge_robot_arm.vision.model_resolver import compatible_chat_generation
    from cloud_edge_robot_arm.vision.planner import VisualDecision, compatible_messages
    messages = build_visual_messages(request.user_instruction, frame.observation,
        image_size=(320, 240), coordinate_system='normalized_1000',
        decision_schema=VisualDecision.model_json_schema())
    body = {'model': settings['model'], 'messages': compatible_messages(messages),
            **compatible_chat_generation(settings['model'], settings['generation_parameters']),
            'response_format': {'type': 'json_object'}}
    assert set(body) == {'model', 'messages', 'reasoning_effort', 'max_completion_tokens', 'response_format'}
    assert len(json.dumps(body).encode()) <= 2000000
    images = []
    for message in body['messages']:
        content = message.get('content')
        if isinstance(content, list):
            for part in content:
                if part.get('type') == 'image_url':
                    url = part['image_url']['url']
                    assert url.startswith('data:image/png;base64,')
                    data = base64.b64decode(url.split(',', 1)[1], validate=True)
                    with Image.open(io.BytesIO(data)) as image:
                        assert image.format == 'PNG' and image.size == (320, 240)
                        image.verify()
                    images.append(data)
    assert len(images) == 2 and images[0] != images[1]
    return body


def attempt_gates(attempt, body, settings, completed_tokens):
    from scripts import probe_rgbd_roles as probe
    directory = Path(attempt['artifact_directory'])
    assert json.loads((directory / 'attempt.json').read_bytes()) == attempt
    assert attempt['status'] == 'COMPLETE' and not attempt.get('wire_artifact_suppressed', False)
    assert all(attempt.get(name) is True for name in (
        'transport_two_images', 'parsed', 'grounded', 'target_hit', 'destination_hit'))
    assert attempt['parse_error'] is None
    assert attempt['request_summary'] == attempt['expected_request_summary'] == probe.summarize_role_request(body)
    assert (directory / 'request.raw').read_bytes() == json.dumps(body).encode()
    contract = attempt['parsed_json']
    assert isinstance(contract, dict) and contract.get('steps')
    pending = [contract]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            assert '_sentinel' not in value
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    skills = [step['skill'] for step in contract['steps']]
    if skills and skills[0] == 'HOME': skills = skills[1:]
    if skills and skills[-1] == 'HOME': skills = skills[:-1]
    assert skills == ['MOVE_ABOVE', 'APPROACH', 'GRASP', 'LIFT', 'MOVE_TO_REGION', 'PLACE', 'RELEASE', 'RETREAT']
    evidence = attempt['observation_evidence']
    for name in ('grounded_target', 'grounded_destination'):
        point = evidence[name]
        assert all(type(point[axis]) in (float, int) and math.isfinite(point[axis]) for axis in ('x', 'y', 'z'))
    for name in ('original_pixel_target', 'original_pixel_destination'):
        point = evidence[name]
        assert len(point) == 2 and all(type(value) is int for value in point)
        assert 0 <= point[0] < 320 and 0 <= point[1] < 240
    assert evidence['top_grasp_offset_status'] == 'CALIBRATED_RGBD_TOP_GRASP_V1'
    assert evidence['grasp_calibration_asset_sha256'] == PLAN['scene']['sha256']
    response_raw = (directory / 'response.raw').read_bytes()
    assert len(response_raw) <= 2000000
    response = json.loads(response_raw)
    assert not response.get('error') and response['choices']
    choice = response['choices'][0]
    assert choice['finish_reason'] == 'stop' and not choice['message'].get('refusal')
    assert isinstance(choice['message']['content'], str) and choice['message']['content']
    usage = response['usage']
    assert all(type(usage[name]) is int and usage[name] >= 0 for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
    assert usage['completion_tokens'] <= 4096 and completed_tokens + usage['completion_tokens'] <= 16384
    requests = attempt['cost_ledger']['requests']
    assert len(requests) == 1
    cost = requests[0]
    assert cost['status'] == 'SUCCESS' and cost['model_role'] == 'PLANNER'
    assert cost['provider_location'] == 'REMOTE_SERVICE' and cost['sent_at'] is not None
    assert cost['provider_version'] == evidence['model_snapshot_hash']
    assert cost['serialized_sent_bytes'] == len((directory / 'request.raw').read_bytes())
    assert cost['serialized_received_bytes'] == len(response_raw)
    assert attempt['actual_request_settings'] == settings
    return usage['completion_tokens']


def journal():
    path = RAW / 'runtime-events.jsonl'
    if not path.exists():
        return []
    # Only complete append records are visible to the live supervisor.
    rows = []
    with path.open('rb') as stream:
        for line in stream:
            deadline_check()
            if line.endswith(b'\n'):
                rows.append(json.loads(line))
    return rows


def operation_counts(rows, snapshot=None, *, forced_loss=False):
    source = None if snapshot is None else snapshot['ledger']
    slots = {} if snapshot is None else {slot['slot_id']: slot for slot in snapshot['slots']}
    loss = forced_loss or snapshot is None or bool(snapshot.get('evidence_loss') or snapshot.get('failures'))
    intent_loss = False
    # Durable intent is mandatory before every possible camera-producing call.
    for path in sorted((RAW / 'call-slots').glob('*.intent.json')):
        deadline_check()
        try:
            slot = json.loads(path.read_bytes())
            if slot['slot_id'] not in slots:
                slots[slot['slot_id']] = slot | {'state': 'POSSIBLY_ENTERED', 'capture_operation_ids': []}
                loss = True
        except (ValueError, KeyError):
            loss = True
            intent_loss = True
    observed = [row for row in rows if row['event'] == 'BACKEND_OPERATION']
    ledger = source or []
    ids = {row['operation_id'] for row in ledger+observed if row['kind'] == 'CAPTURE'}
    associations = {}
    for slot_id, slot in slots.items():
        for number in slot.get('capture_operation_ids', []):
            associations.setdefault(number, set()).add(slot_id)
    for row in observed:
        if row['kind'] == 'CAPTURE' and row.get('slot_id') in slots:
            associations.setdefault(row['operation_id'], set()).add(row['slot_id'])
    covered = (snapshot is not None and not intent_loss and len(slots) <= 5
               and all(slot['render_ceiling'] in (2, 3) for slot in slots.values()))
    lower = completed = unknown = 0
    upper = 0
    for slot_id, slot in slots.items():
        numbers = {number for number in ids if associations.get(number) == {slot_id}}
        if len(numbers) > 1:
            covered = False
        proven = 0
        exact_slot = slot['state'] == 'RETURNED' and len(numbers) == 1
        if slot['state'] == 'NOT_ENTERED' and not numbers:
            exact_slot = True
        for number in numbers:
            events = [row for row in observed if row['kind'] == 'CAPTURE' and row['operation_id'] == number]
            ends = [row for row in events if row['phase'] == 'END']
            begins = [row for row in events if row['phase'] == 'BEGIN']
            source_events = [row for row in ledger if row['kind'] == 'CAPTURE' and row['operation_id'] == number]
            source_begins = [row for row in source_events if row['phase'] == 'BEGIN']
            source_ends = [row for row in source_events if row['phase'] == 'END']
            valid_end = (len(ends) == 1 and ends[0]['error_type'] is None and
                ends[0]['pass_count'] == slot['render_ceiling'] and
                len(ends[0]['pass_state_hashes']) == slot['render_ceiling'] and
                len(set(ends[0]['pass_state_hashes'])) == 1)
            if valid_end:
                proven += ends[0]['pass_count']
                completed += 1
            exact_slot = (exact_slot and valid_end and len(begins) == 1 and
                len(source_begins) == 1 and len(source_ends) == 1 and
                source_ends[0]['error_type_sha256'] is None)
        lower += proven
        if exact_slot:
            upper += proven
        else:
            loss = True
            unknown += 1
            upper += max(proven, slot['render_ceiling'])
    if any(len(associations.get(number, set())) != 1 for number in ids):
        covered = False
        loss = True
    all_operations = {(row['operation_id'], row['kind'], row['phase']) for row in ledger+observed}
    complete = not loss and covered
    return {'reset_invoked': len({number for number, kind, phase in all_operations
                                 if kind == 'RESET' and phase == 'BEGIN'}),
        'captures_invoked': len(ids), 'captures_completed': completed,
        'implicit_captures_invoked': sum(associations.get(number) == {slot['slot_id']}
            for number in ids for slot in slots.values() if slot['render_ceiling'] == 2),
        'explicit_captures_invoked': sum(associations.get(number) == {slot['slot_id']}
            for number in ids for slot in slots.values() if slot['render_ceiling'] == 3),
        'render_completed_lower_bound': lower, 'render_upper_bound': upper if covered else None,
        'render_exact': lower if complete else None, 'capture_unknown_intervals': unknown,
        'evidence_complete': complete, 'unbounded_or_uncovered_evidence': not covered,
        'invocation_counts_are_observed_lower_bounds': not complete,
        'planned_render_ceiling': 14,
        'forbidden_operation_count': sum(kind in ('CONTROL', 'PHYSICS', 'COMMAND')
                                         for _, kind, _ in all_operations)}


def safe_backend_metadata(backend):
    ledger = []
    failures = []
    for target, source in ((ledger, backend.operation_ledger),
                           (failures, backend.operation_observer_failures)):
        for row in source:
            result = {}
            for name in ('operation_id', 'physics_step'):
                if name in row:
                    assert type(row[name]) is int and row[name] >= 0
                    result[name] = row[name]
            for name, allowed in (('kind', ('RESET', 'CONTROL', 'PHYSICS', 'COMMAND', 'CAPTURE')),
                                  ('phase', ('BEGIN', 'END'))):
                assert row[name] in allowed
                result[name] = row[name]
            if 'episode_id' in row:
                assert row['episode_id'] is None or isinstance(row['episode_id'], str)
                result['episode_id'] = row['episode_id']
            for name in ('error_type', 'observer_error_type'):
                if name in row:
                    result[name+'_sha256'] = None if row[name] is None else digest(str(row[name]))
            target.append(result)
    return ledger, failures


def execute_child(key, admitted_at):
    from scripts import probe_rgbd_roles as probe
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame
    from cloud_edge_robot_arm.vision.role_models import cloud_request_settings
    from cloud_edge_robot_arm.vision.top_grasp import matches_calibrated_gripper

    def stop(signum, frame):
        raise InterruptedError('owned worker interrupted')

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # The probe has no workload subprocesses. Reject Python process creation.
    def no_process(event_name, args):
        if event_name in ('subprocess.Popen', 'os.fork', 'os.forkpty', 'os.system',
                          'os.posix_spawn', 'os.exec'):
            raise RuntimeError('unexpected workload subprocess')
    sys.addaudithook(no_process)
    config = json.loads((HERE / 'frozen-role-config.json').read_bytes())
    metadata = json.loads((HERE / 'profile-metadata.json').read_bytes())
    report = new_report(config)
    report['config_sha256'] = sha(HERE / 'frozen-role-config.json')
    binding = None
    backend = None
    closed = False
    initialized = False
    context = {'capture': 'RESET'}
    observed_frames = []
    completion_tokens = 0
    operation_failures = []
    physics_steps = None
    accounting = {'slots': [], 'sequence': 0, 'evidence_loss': False, 'snapshot': None}

    def snapshot():
        ledger, failures = safe_backend_metadata(backend)
        value = {'ledger': ledger, 'failures': failures,
            'slots': json.loads(json.dumps(accounting['slots'])),
            'evidence_loss': accounting['evidence_loss']}
        accounting['snapshot'] = value
        number = accounting['sequence']
        accounting['sequence'] += 1
        try:
            save(RAW / f'operation-snapshots/{number:04d}.json', value)
        except BaseException:
            accounting['evidence_loss'] = True
            value['evidence_loss'] = True
            raise
        return value

    def call_slot(kind, index, callback):
        snapshot()
        before = max((row['operation_id'] for row in backend.operation_ledger), default=0)
        slot = {'slot_id': len(accounting['slots']), 'kind': kind, 'index': index,
            'render_ceiling': 2 if kind == 'RESET' else 3,
            'ledger_max_id_before': before, 'state': 'NOT_ENTERED', 'capture_operation_ids': []}
        save(RAW / f"call-slots/{slot['slot_id']:02d}.intent.json", slot)
        accounting['slots'].append(slot)
        context.update(capture=kind, slot_id=slot['slot_id'])
        slot['state'] = 'POSSIBLY_ENTERED'
        try:
            value = callback()
        except BaseException:
            slot['state'] = 'RAISED'
            raise
        else:
            slot['state'] = 'RETURNED'
            return value
        finally:
            slot['capture_operation_ids'] = sorted({row['operation_id'] for row in backend.operation_ledger
                if row['operation_id'] > before and row['kind'] == 'CAPTURE'})
            slot['ledger_max_id_after'] = max((row['operation_id'] for row in backend.operation_ledger), default=0)
            try:
                save(RAW / f"call-slots/{slot['slot_id']:02d}.finished.json", slot)
            finally:
                snapshot()

    def observe(boundary):
        result = boundary.result or {}
        sensor = result.get('sensor_frame') or {}
        hashes = tuple(result.get('pass_state_hashes') or ())
        event('BACKEND_OPERATION', operation_id=boundary.operation_id, kind=boundary.kind,
              phase=boundary.phase, episode_id=boundary.episode_id,
              physics_step=boundary.physics_step, sim_time_s=boundary.sim_time_s,
              error_type=boundary.error_type, capture_context=context['capture'],
              slot_id=context.get('slot_id'),
              frame_id=sensor.get('frame_id'), pass_count=len(hashes), pass_state_hashes=list(hashes))

    def check():
        current_snapshot = snapshot()
        ready()
        checkpoint(admitted_at, binding.planner, binding.settings)
        assert backend.total_physics_steps == 0 and not backend.operation_observer_failures
        counts = operation_counts(journal(), current_snapshot,
                                  forced_loss=accounting['evidence_loss'])
        assert counts['evidence_complete']
        assert counts['forbidden_operation_count'] == 0 and counts['reset_invoked'] <= 1
        assert counts['implicit_captures_invoked'] <= 1 and counts['explicit_captures_invoked'] <= 4
        assert counts['render_upper_bound'] <= 14
        assert all(row['pass_count'] == (2 if row['capture_context'] == 'RESET' else 3)
                   for row in journal() if row['event'] == 'BACKEND_OPERATION' and
                   row['kind'] == 'CAPTURE' and row['phase'] == 'END' and row['error_type'] is None)

    try:
        receipt = ready()
        binding = bindings(metadata, config, key)
        assert binding.store.has_secret(binding.profile.profile_id)
        assert binding.settings == receipt['request_settings']
        assert binding.bundle.evidence() == receipt['bundle']
        report.update(bundle=binding.bundle.evidence(), bundle_hash=binding.bundle.digest(),
            edge_snapshot=binding.edge.evidence(), edge_policy=config['edge']['policy'],
            device_source_hashes=binding.device, request_settings=binding.settings, transport='REAL_HTTP')
        checkpoint(admitted_at, binding.planner, binding.settings)
        simulator = SimulatorConfig(camera_width=320, camera_height=240, render_rgb=True,
            render_depth=True, domain_randomization=False, seed=0, model_path=PLAN['scene']['model_path'])
        backend = MuJoCoPhysicsBackend()
        event('INITIALIZE_BEGIN')
        backend.initialize(simulator)
        initialized = True
        event('INITIALIZE_END')
        assert matches_calibrated_gripper(backend._model, 'mujoco_upright_box_v2')
        with backend.observe_operation_boundaries(observe):
            call_slot('RESET', None,
                lambda: backend.reset(PhysicalScenarioConfig.scenario('S01_NORMAL_STATIC', seed=0)))
            check()
            with MuJoCoCaptureSession(simulator, backend=backend) as session:
                for index in range(4):
                    check()
                    context['capture'] = 'EXPLICIT'
                    event('CAPTURE_BOUNDARY', index=index)
                    frame = call_slot('EXPLICIT', index, session.capture_with_instances)
                    observation = frame.observation
                    identity = {'frame_id': observation.frame_id,
                        'captured_at': observation.captured_at.isoformat(),
                        'episode_id': observation.episode_id, 'scene_id': observation.scene_id,
                        'sim_time_s': observation.sim_time_s, 'physics_state_hash': frame.physics_state_hash,
                        'observation_sha256': observation.checksum_sha256}
                    event('FRESH_FRAME_RETURNED', index=index, **identity)
                    try:
                        assert observation.source == 'mujoco_camera' and (observation.width, observation.height) == (320, 240)
                        assert observation.scene_id == 'S01_NORMAL_STATIC' and observation.episode_id
                        assert observation.sim_time_s == 0
                        assert len(frame.pass_state_hashes) == 3 and set(frame.pass_state_hashes) == {frame.physics_state_hash}
                        assert all(row['frame_id'] != identity['frame_id'] and
                                   row['captured_at'] != identity['captured_at'] and
                                   row['episode_id'] == identity['episode_id'] and
                                   row['physics_state_hash'] == identity['physics_state_hash']
                                   for row in observed_frames)
                        check()
                        request = InitialPlanningRequest(request_id=f'cloud-role-probe-{index:02d}',
                            user_instruction=config['probe']['instruction'], observation=observation,
                            scene=SceneSummary(scene_version=1, updated_at=observation.captured_at))
                        body = expected_body(request, frame, binding.settings)
                        check()
                    except BaseException:
                        # Preserve the actual captured frame, without inventing an attempt.
                        save_captured_frame(frame, RAW / f'capture-failed-before-api-{index:02d}')
                        raise
                    observed_frames.append(identity)
                    report['source'] = observation.source
                    report['capture'] = {'synchronized': True, 'image_size': [320, 240]}
                    event('REQUEST_BOUNDARY', index=index, model='gpt-6.1-sol')
                    event('ATTEMPT_BEGIN', index=index)
                    attempt = probe._attempt(binding.planner, request, frame, RAW, index,
                                             binding.cloud, request_settings=binding.settings)
                    report['attempts'].append(attempt)
                    # Original returned attempt is persisted before evaluating any gate.
                    probe._write(RAW / f'progress-{index:02d}.json',
                                 probe._safe_attempt_record(report, key))
                    event('ATTEMPT_RETURNED', index=index)
                    completion_tokens += attempt_gates(attempt, body, binding.settings, completion_tokens)
                    check()
                    event('ATTEMPT_GATES_PASSED', index=index)
            check()
            counts = operation_counts(journal(), snapshot(), forced_loss=accounting['evidence_loss'])
            assert counts['reset_invoked'] == 1 and counts['captures_completed'] == 5
            assert counts['implicit_captures_invoked'] == 1 and counts['explicit_captures_invoked'] == 4
            assert counts['render_exact'] == 14 and counts['capture_unknown_intervals'] == 0
            report['final_request_settings'] = cloud_request_settings(binding.planner)
            report['status'] = 'PASS' if probe.can_accept_role_probe(report) else 'FAIL'
    except BaseException as error:
        report.update(status='BLOCKED', blocked_reason=type(error).__name__)
        event('WORKER_STOPPED', failure_class_sha256=digest(type(error).__name__))
    finally:
        if backend is not None:
            try:
                physics_steps = backend.total_physics_steps
                snapshot()
                _, operation_failures = safe_backend_metadata(backend)
            except BaseException:
                accounting['evidence_loss'] = True
            try:
                try:
                    event('SHUTDOWN_BEGIN')
                except BaseException:
                    accounting['evidence_loss'] = True
                backend.shutdown()
                closed = True
            except BaseException as error:
                report.update(status='BLOCKED', shutdown_failure_class_sha256=digest(type(error).__name__))
            finally:
                try:
                    snapshot()
                    event('SHUTDOWN_END', backend_closed=closed)
                except BaseException:
                    accounting['evidence_loss'] = True
        try:
            report.update(finished_at=datetime.now(UTC).isoformat(),
                unexecuted_attempt_count=4-len(report['attempts']))
            safe_report = probe._safe_attempt_record(report, key)
        finally:
            try:
                if binding is not None:
                    binding.store.delete_secret(binding.profile.profile_id)
                    assert not binding.store.has_secret(binding.profile.profile_id)
            finally:
                if binding is not None:
                    binding.planner._api_key = ''
                key = ''
                binding = None
        try:
            event('SECRET_REMOVED_FROM_STORE')
        except BaseException:
            accounting['evidence_loss'] = True
    checksum = probe._write(RAW / 'role-probe-report.json', safe_report)
    with (RAW / 'role-probe-report.sha256').open('x') as stream:
        stream.write(checksum + '\n')
    if safe_report.get('status') == 'PASS':
        probe._write(RAW / 'roles-frozen.json', safe_report['bundle'])
    save(RAW / 'worker-result.json', {'status': safe_report.get('status'),
        'initialized': initialized, 'backend_closed': closed, 'secret_store_removed': True,
        'physics_steps': physics_steps, 'operation_observer_failure_hashes': [digest(row) for row in operation_failures],
        'operation_observer_failures_safe': operation_failures,
        'last_safe_snapshot': accounting['snapshot'], 'accounting_evidence_loss': accounting['evidence_loss'],
        'counts': operation_counts(journal(), accounting['snapshot'], forced_loss=accounting['evidence_loss']),
        'source_generation': json.loads((HERE / 'preflight.json').read_bytes())['source_generation'],
        'fresh_frames': observed_frames,
        'completion_tokens_from_successful_gate_checks': completion_tokens,
        'elapsed_s': time.monotonic()-admitted_at,
        'peak_self_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024})
    event('WORKER_COMPLETE', status=safe_report.get('status'))
    return 0 if safe_report.get('status') == 'PASS' else 2


def worker_interrupt(number, frame):
    raise InterruptedError('owned worker interrupted')


def process_identity(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')')+2:].split()
        pages = Path(f'/proc/{pid}/statm').read_text().split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
            'starttime': int(fields[19]), 'rss_bytes': int(pages[1])*os.sysconf('SC_PAGE_SIZE')}


def owner_event(name, **fields):
    try:
        with (HERE / 'ownership-events.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': name, 'monotonic': time.monotonic(), **fields})+'\n')
            stream.flush()
    except BaseException:
        if SUPERVISION is not None:
            SUPERVISION['evidence_io_loss'] = True


def pid_exited(entry):
    return bool(select.select([entry['pidfd']], [], [], 0)[0])


def pin_process(pid):
    before = process_identity(pid)
    if before is None:
        return None
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        owner_event('EXIT_BEFORE_PIDFD', pid=pid, starttime=before['starttime'])
        return None
    after = process_identity(pid)
    if after is None or after['starttime'] != before['starttime']:
        os.close(descriptor)
        owner_event('EXIT_OR_REUSE_WHILE_PINNING', pid=pid, starttime=before['starttime'])
        return None
    return {'identity': before, 'pidfd': descriptor, 'signals': []}


def children_of(identity, entry=None):
    current = process_identity(identity['pid'])
    if current is None:
        if entry is not None and pid_exited(entry):
            return []
        raise RuntimeError('unresolved parent identity')
    if current['starttime'] != identity['starttime']:
        if entry is not None and pid_exited(entry):
            return []
        raise RuntimeError('parent PID identity changed')
    result = set()
    try:
        for task in Path(f"/proc/{identity['pid']}/task").iterdir():
            try:
                result.update(int(pid) for pid in (task / 'children').read_text().split())
            except (FileNotFoundError, ProcessLookupError):
                # A thread can exit during enumeration; its children reparent.
                continue
    except (FileNotFoundError, ProcessLookupError):
        if entry is not None and pid_exited(entry):
            return []
        raise
    return sorted(result)


def terminate_owned(known, state, stopping_at):
    for entry in known.values():
        if pid_exited(entry):
            continue
        sent = {row['signal'] for row in entry['signals']}
        number = (signal.SIGKILL if time.monotonic()-stopping_at >= 2 or
                  time.monotonic() >= state['outer_deadline']-2 else signal.SIGTERM)
        if int(number) not in sent:
            try:
                signal.pidfd_send_signal(entry['pidfd'], number)
            except ProcessLookupError:
                pass
            item = {'signal': int(number), 'monotonic': time.monotonic()}
            entry['signals'].append(item)
            owner_event('TARGETED_SIGNAL', identity=entry['identity'], **item)


def discover_owned(supervisor, known):
    todo = [(supervisor, None)]
    visited = set()
    tree = []
    while todo:
        deadline_check()
        parent, parent_entry = todo.pop()
        parent_key = (parent['pid'], parent['starttime'])
        if parent_key in visited:
            continue
        visited.add(parent_key)
        for pid in children_of(parent, parent_entry):
            current = process_identity(pid)
            if current is None:
                owner_event('CHILD_EXITED_BEFORE_METADATA', pid=pid)
                continue
            key = (pid, current['starttime'])
            if key in known:
                entry = known[key]
            else:
                entry = pin_process(pid)
                if entry is None:
                    continue
                current = entry['identity']
                if current['ppid'] not in (parent['pid'], supervisor['pid']):
                    os.close(entry['pidfd'])
                    raise RuntimeError('candidate ownership unresolved')
                key = (pid, current['starttime'])
                known[key] = entry
                owner_event('OWNED_IDENTITY_FIXED', identity=entry['identity'])
            if SUPERVISION is not None:
                state = SUPERVISION
                if key != state.get('worker_key') and current['pid'] != state.get('worker_pid'):
                    state['unexpected_descendant'] = True
                    state.setdefault('early_stopping_at', time.monotonic())
                if time.monotonic() >= state['child_deadline'] or state['cancel_signal'] is not None or state['outer_hit']:
                    state.setdefault('early_stopping_at', time.monotonic())
                if 'early_stopping_at' in state:
                    terminate_owned(known, state, state['early_stopping_at'])
            tree.append(current)
            if not pid_exited(entry):
                todo.append((entry['identity'], entry))
    return {row['pid']: row for row in tree}


def seal_raw():
    files = []
    for path in RAW.rglob('*'):
        deadline_check()
        if path.is_symlink():
            raise ValueError('symlink in raw evidence')
        if path.is_file():
            files.append({'path': str(path.relative_to(RAW)), 'bytes': path.stat().st_size,
                          'sha256': sha(path)})
    deadline_check()
    return sorted(files, key=lambda row: row['path'])


def admission():
    output = HERE / 'resource-admission'
    output.mkdir()
    rows = []
    for index, command in enumerate(PLAN['runtime_admission']['resource_queries_once']):
        import shlex
        started = time.monotonic()
        try:
            result = subprocess.run(shlex.split(command), capture_output=True,
                                    timeout=8, check=False)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code = error.stdout or b'', error.stderr or b'', None
        for name, data in (('stdout', stdout), ('stderr', stderr)):
            with (output / f'{index:02d}.{name}').open('xb') as stream:
                stream.write(data)
        rows.append({'command': command, 'returncode': code, 'elapsed_s': time.monotonic()-started,
                     'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                     'stderr_sha256': hashlib.sha256(stderr).hexdigest()})
    save(output / 'commands.json', rows)
    assert all(row['returncode'] == 0 for row in rows)
    gpu_rows = list(csv.reader((output / '00.stdout').read_text().splitlines()))
    gpu = next(row for row in gpu_rows if row[0].strip() == '0')
    assert float(gpu[4].strip()) >= 2048
    assert not (output / '01.stdout').read_text().strip()
    unit = dict(line.split('=', 1) for line in (output / '02.stdout').read_text().splitlines() if '=' in line)
    assert unit['LoadState'] == 'loaded' and unit['ActiveState'] == 'inactive' and unit['SubState'] == 'dead'
    assert unit['MainPID'] == unit['ControlPID'] == '0'
    assert shutil.disk_usage(ROOT).free >= 2147483648
    save(output / 'gate.json', {'status': 'ADMITTED', 'gpu0_free_MiB': float(gpu[4].strip()),
        'disk_free_bytes': shutil.disk_usage(ROOT).free, 'utc': datetime.now(UTC).isoformat()})


def supervise(supervisor, worker_pid, known, state, initial_reason=None):
    audit = state.setdefault('audit', {'reason': None, 'reaps': [], 'worker_reap': None,
        'peak_rss': 0, 'maximum_interval': 0.0, 'last_sample': None, 'samples_taken': 0,
        'stopping_at': None, 'unresolved_written': False, 'had_unresolved': False,
        'last_raw_bytes': None})
    reason = audit['reason'] or initial_reason
    reaps = audit['reaps']
    worker_reap = audit['worker_reap']
    peak_rss = audit['peak_rss']
    maximum_interval = audit['maximum_interval']
    last_sample = audit['last_sample']
    samples_taken = audit['samples_taken']
    empty_cycles = 0
    stopping_at = audit['stopping_at']
    unresolved_written = audit['unresolved_written']
    had_unresolved = audit['had_unresolved']
    last_raw_bytes = audit['last_raw_bytes']
    try:
        sample_path = HERE / 'resource-samples.jsonl'
        samples = sample_path.open('a' if sample_path.exists() else 'x')
    except OSError:
        samples = None
        state['evidence_io_loss'] = True
    try:
        while True:
            now = time.monotonic()
            if now >= state['outer_deadline']:
                state['outer_hit'] = True
            if state['cancel_signal'] is not None:
                reason = reason or 'CANCELLED_SIGNAL'
            if now >= state['child_deadline'] and worker_reap is None:
                reason = reason or 'CHILD_WALL_BUDGET'
            if state['outer_hit']:
                reason = reason or 'OUTER_DEADLINE'
            if state['evidence_io_loss']:
                reason = reason or 'SUPERVISOR_EVIDENCE_IO_LOSS'
            if state.get('unexpected_descendant'):
                reason = reason or 'UNEXPECTED_DESCENDANT'
            metadata_unknown = False
            no_children = False
            try:
                state['phase'] = 'CLEANUP' if stopping_at is not None else 'ACTIVE'
                tree = discover_owned(supervisor, known)
                before_children = children_of(supervisor)
                if any(entry['identity']['pid'] != worker_pid or
                       (state.get('worker_key') is not None and key != state['worker_key'])
                       for key, entry in known.items()):
                    reason = reason or 'UNEXPECTED_DESCENDANT'
                # Every reap is nonblocking; adopted children are drained too.
                while True:
                    deadline_check()
                    try:
                        pid, status, usage = os.wait4(-1, os.WNOHANG)
                    except ChildProcessError:
                        no_children = True
                        break
                    if pid == 0:
                        break
                    candidates = [entry for entry in known.values() if entry['identity']['pid'] == pid]
                    entry = candidates[-1] if candidates else None
                    item = {'pid': pid, 'identity': entry['identity'] if entry else None,
                        'status': status, 'returncode': os.waitstatus_to_exitcode(status),
                        'ru_maxrss_bytes': usage.ru_maxrss*1024,
                        'reaped_monotonic': time.monotonic(),
                        'elapsed_s': time.monotonic()-state['started']}
                    reaps.append(item)
                    if pid == worker_pid and worker_reap is None:
                        worker_reap = item
                        audit['worker_reap'] = item
                        if item['returncode'] != 0:
                            reason = reason or 'WORKER_NONZERO'
                    elif entry is None:
                        reason = reason or 'UNEXPECTED_ADOPTED_REAP_UNKNOWN_STARTTIME'
                    if item['ru_maxrss_bytes'] > 4294967296:
                        reason = reason or 'WAIT4_RSS_BUDGET'
                    owner_event('REAP', **item)
                    # Reparented children must be rediscovered after every reap.
                    tree.update(discover_owned(supervisor, known))
                tree.update(discover_owned(supervisor, known))
                after_children = children_of(supervisor)
            except BaseException as error:
                metadata_unknown = True
                reason = reason or 'OWNERSHIP_METADATA_' + digest(type(error).__name__)
                tree, before_children, after_children = {}, [None], [None]
            alive = [entry for entry in known.values() if not pid_exited(entry)]
            closed_cycle = (worker_reap is not None and no_children and not before_children and
                not after_children and not alive and not metadata_unknown)
            empty_cycles = empty_cycles+1 if closed_cycle else 0
            if empty_cycles >= 2:
                state['phase'] = 'CLOSED'
                return {'reason': reason, 'worker_reap': worker_reap, 'reaps': reaps,
                    'peak_sampled_tree_RSS_bytes': peak_rss, 'samples_taken': samples_taken,
                    'maximum_sampling_interval_s': maximum_interval, 'closure_confirmed': True,
                    'empty_ECHILD_cycles': empty_cycles, 'outer_hit': state['outer_hit'],
                    'had_unresolved_deadline': had_unresolved,
                    'closed_monotonic': time.monotonic(), 'last_sampled_raw_bytes': last_raw_bytes}
            if not state['outer_hit']:
                try:
                    state['phase'] = 'SCAN'
                    current = time.monotonic()
                    if last_sample is not None:
                        maximum_interval = max(maximum_interval, current-last_sample)
                    last_sample = current
                    rss = sum(row['rss_bytes'] for row in tree.values() if row['state'] != 'Z')
                    peak_rss = max(peak_rss, rss)
                    raw_bytes = size(RAW)
                    last_raw_bytes = raw_bytes
                    free = shutil.disk_usage(ROOT).free
                    rows = journal()
                    begun = [row for row in rows if row['event'] == 'ATTEMPT_BEGIN']
                    returned = {row['index'] for row in rows if row['event'] == 'ATTEMPT_RETURNED'}
                    inflight = [row for row in begun if row['index'] not in returned]
                    sample = {'monotonic': current, 'wall_s': current-state['started'],
                        'tree': list(tree.values()), 'rss_bytes': rss, 'raw_bytes': raw_bytes,
                        'disk_free_bytes': free, 'inflight_attempt_indices': [row['index'] for row in inflight]}
                    if samples is not None:
                        samples.write(json.dumps(sample)+'\n')
                        samples.flush()
                    samples_taken += 1
                    if rss > 4294967296 or raw_bytes > 1073741824 or free < 2147483648:
                        reason = reason or 'RESOURCE_BUDGET'
                    if any(current-row['monotonic'] > 185 for row in inflight):
                        reason = reason or 'REQUEST_WATCHDOG'
                    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024 > 4294967296:
                        reason = reason or 'SUPERVISOR_RSS_BUDGET'
                    deadline_check()
                except BaseException as error:
                    reason = reason or 'SUPERVISION_SCAN_' + digest(type(error).__name__)
                finally:
                    state['phase'] = 'CLEANUP' if stopping_at is not None else 'ACTIVE'
            if reason or worker_reap is not None:
                if stopping_at is None:
                    stopping_at = state.get('early_stopping_at', time.monotonic())
                state['phase'] = 'CLEANUP'
                terminate_owned(known, state, stopping_at)
            if state['outer_hit'] and not unresolved_written:
                had_unresolved = True
                receipt = {'status': 'OUTER_DEADLINE_UNRESOLVED', 'lock_retained': True,
                    'compliant': False, 'source_generation': state['generation'],
                    'deadline': state['outer_deadline'], 'observed_monotonic': time.monotonic(),
                    'deadline_observation_delay_s': max(0, time.monotonic()-state['outer_deadline']),
                    'worker_reaped': worker_reap is not None, 'metadata_unresolved': metadata_unknown,
                    'owned': [{'identity': entry['identity'], 'signals': entry['signals'],
                               'pidfd_exited': pid_exited(entry)} for entry in known.values()]}
                try:
                    save(HERE / 'outer-deadline-unresolved.json', receipt, exempt=True)
                    unresolved_written = True
                except BaseException:
                    print('OUTER_DEADLINE_UNRESOLVED: GPU lock retained; no new workload', flush=True)
            audit.update(reason=reason, worker_reap=worker_reap, peak_rss=peak_rss,
                maximum_interval=maximum_interval, last_sample=last_sample,
                samples_taken=samples_taken, stopping_at=stopping_at,
                unresolved_written=unresolved_written, had_unresolved=had_unresolved,
                last_raw_bytes=last_raw_bytes)
            time.sleep(1.0 if state['outer_hit'] else 0.2)
    finally:
        audit.update(reason=reason, worker_reap=worker_reap, peak_rss=peak_rss,
            maximum_interval=maximum_interval, last_sample=last_sample,
            samples_taken=samples_taken, stopping_at=stopping_at,
            unresolved_written=unresolved_written, had_unresolved=had_unresolved,
            last_raw_bytes=last_raw_bytes)
        if samples is not None:
            samples.close()


def load_accounting(worker):
    if worker is not None:
        return worker['counts']
    snapshot = None
    for path in sorted((RAW / 'operation-snapshots').glob('*.json')):
        deadline_check()
        try:
            snapshot = json.loads(path.read_bytes())
        except ValueError:
            continue
    return operation_counts(journal(), snapshot, forced_loss=True)


def execute():
    global SUPERVISION
    receipt = ready()
    assert not RAW.exists() and not (HERE / 'supervisor-result.json').exists()
    assert not (HERE / 'execution-start.json').exists()
    assert sys.stdin.isatty(), 'HIDDEN_TTY_REQUIRED'
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('OpenAI API key (hidden; memory only; never paste in chat): ')
    if not key:
        print('WAITING_HIDDEN_TTY_SECRET: empty input; no workload launched', flush=True)
        return 2
    assert len(key) <= 512
    lock = (ROOT / PLAN['paths']['gpu_lock']).open('a')
    known = {}
    pid = None
    closure = None
    state = None
    result = None
    old_handlers = {}
    started = None
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            key = ''
            print('WAITING_GPU_LOCK: no workload launched', flush=True)
            return 2
        ready()
        admission()
        ready()
        assert hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')
        libc = ctypes.CDLL(None, use_errno=True)
        assert libc.prctl(36, 1, 0, 0, 0) == 0
        flag = ctypes.c_int(0)
        assert libc.prctl(37, ctypes.byref(flag), 0, 0, 0) == 0 and flag.value == 1
        supervisor = process_identity(os.getpid())
        assert supervisor is not None and not children_of(supervisor)
        started = time.monotonic()
        state = {'started': started, 'child_deadline': started+900, 'outer_deadline': started+960,
            'outer_hit': False, 'cancel_signal': None, 'phase': 'ACTIVE',
            'generation': receipt['source_generation'], 'evidence_io_loss': False, 'worker_key': None}
        SUPERVISION = state
        def cancel(number, frame):
            state['cancel_signal'] = number
        def outer_alarm(number, frame):
            state['outer_hit'] = True
            if state['phase'] == 'SEAL':
                raise OuterDeadline()
        for number in (signal.SIGINT, signal.SIGTERM):
            old_handlers[number] = signal.signal(number, cancel)
        old_handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, outer_alarm)
        signal.setitimer(signal.ITIMER_REAL, max(.001, state['outer_deadline']-time.monotonic()))
        RAW.mkdir(parents=True)
        save(HERE / 'execution-start.json', {'utc': datetime.now(UTC).isoformat(),
            'source_generation': receipt['source_generation'], 'runner_sha256': sha(Path(__file__)),
            'planned_attempt_count': 4, 'admitted_monotonic': started,
            'supervisor_identity': supervisor, 'subreaper_verified': True,
            'initial_children': [], 'child_deadline': state['child_deadline'],
            'outer_deadline': state['outer_deadline']})
        pid = os.fork()
        if pid == 0:
            try:
                SUPERVISION = None
                signal.signal(signal.SIGTERM, worker_interrupt)
                signal.signal(signal.SIGINT, worker_interrupt)
                os.setsid()
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)
                lock.close()
                stdout = os.open(RAW / 'worker.stdout', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                stderr = os.open(RAW / 'worker.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.dup2(stdout, 1)
                os.dup2(stderr, 2)
                os.close(stdout)
                os.close(stderr)
                code = execute_child(key, started)
            except BaseException as error:
                key = ''
                try:
                    event('WORKER_OUTER_FAILURE', failure_class_sha256=digest(type(error).__name__))
                except BaseException:
                    pass
                code = 2
            os._exit(code)
        key = ''
        state['worker_pid'] = pid
        entry = pin_process(pid)
        if entry is not None:
            worker_key = (pid, entry['identity']['starttime'])
            known[worker_key] = entry
            state['worker_key'] = worker_key
            owner_event('WORKER_IDENTITY_FIXED', identity=entry['identity'])
        closure = supervise(supervisor, pid, known, state)
    except BaseException as error:
        key = ''
        failure = 'SUPERVISOR_FAILURE_' + digest(type(error).__name__)
        if pid is not None and pid != 0 and closure is None:
            # Ownership stays here until confirmed closure, including deadline failure.
            closure = supervise(supervisor, pid, known, state, initial_reason=failure)
        else:
            save(HERE / 'admission-stopped.json', {'reason': failure, 'workload_started': False,
                'API': 0, 'render': 0, 'physics': 0}, exempt=True)
    finally:
        key = ''
        try:
            if pid is not None and pid != 0:
                assert closure is not None and closure['closure_confirmed']
                state['phase'] = 'CLOSED'
                save(HERE / 'process-closure.json', {'source_generation': receipt['source_generation'],
                    'closure': closure, 'owned': [{'identity': entry['identity'],
                    'pidfd_exited': pid_exited(entry), 'signals': entry['signals']} for entry in known.values()]},
                    exempt=True)
                late = closure['outer_hit'] or time.monotonic() >= state['outer_deadline']
                if late:
                    save(HERE / 'late-closure.json', {'status': 'LATE_CLOSURE_NO_SEAL_OR_READER',
                        'source_generation': receipt['source_generation'], 'closure': closure,
                        'lock_release_allowed_after_closure': True, 'compliant': False}, exempt=True)
                else:
                    seal_complete = False
                    pins_ok = False
                    worker = None
                    raw_bytes = None
                    counts = None
                    request_counts = None
                    try:
                        state['phase'] = 'SCAN'
                        ready()
                        pins_ok = True
                        worker_path = RAW / 'worker-result.json'
                        worker = json.loads(worker_path.read_bytes()) if worker_path.exists() else None
                        counts = load_accounting(worker)
                        rows = journal()
                        begun = {row['index'] for row in rows if row['event'] == 'ATTEMPT_BEGIN'}
                        returned = {row['index'] for row in rows if row['event'] == 'ATTEMPT_RETURNED'}
                        costs = []
                        original_attempts = 0
                        incomplete_attempt_files = 0
                        for path in RAW.glob('attempt-*/attempt.json'):
                            deadline_check()
                            try:
                                attempt = json.loads(path.read_bytes())
                                original_attempts += 1
                                costs.extend(attempt.get('cost_ledger', {}).get('requests', []))
                            except ValueError:
                                incomplete_attempt_files += 1
                        request_counts = {'planned_attempt_count': 4,
                            'attempt_start_boundary_count': len(begun),
                            'attempt_returned_journal_count': len(returned),
                            'complete_original_attempt_files': original_attempts,
                            'incomplete_original_attempt_files': incomplete_attempt_files,
                            'sent_at_known_requests_lower_bound': sum(cost.get('sent_at') is not None for cost in costs),
                            'settled_requests_lower_bound': sum(cost.get('finished_at') is not None for cost in costs),
                            'inflight_attempts_unknown': len(begun-returned),
                            'unexecuted_from_returned_file_denominator': 4-original_attempts,
                            'start_boundary_does_not_prove_sent': True}
                        raw_bytes = size(RAW)
                        state['phase'] = 'SEAL'
                        files = seal_raw()
                        pending = HERE / 'raw-seal.pending.json'
                        save(pending, {'status': 'COMPLETE', 'source_generation': receipt['source_generation'],
                            'raw_root': str(RAW), 'files': files,
                            'mutation_policy': 'Original local-only raw; manifest is not full remote reproduction package'})
                        deadline_check()
                        os.link(pending, HERE / 'raw-seal.json')
                        deadline_check()
                        seal_complete = True
                    except BaseException as error:
                        save(HERE / 'seal-incomplete.json', {'status': 'SEAL_INCOMPLETE',
                            'source_generation': receipt['source_generation'],
                            'failure_class_sha256': digest(type(error).__name__),
                            'outer_hit': state['outer_hit'], 'compliant': False}, exempt=True)
                    finally:
                        state['phase'] = 'CLOSED'
                    observed_peaks = [closure['peak_sampled_tree_RSS_bytes'],
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024]
                    observed_peaks.extend(row['ru_maxrss_bytes'] for row in closure['reaps'])
                    worker_peak = worker.get('peak_self_RSS_bytes') if worker else None
                    worker_peak_valid = type(worker_peak) is int and worker_peak >= 0
                    if worker_peak_valid:
                        observed_peaks.append(worker_peak)
                    peak = max(observed_peaks)
                    wall = time.monotonic()-started
                    worker_reap = closure['worker_reap']
                    compliant = (not closure['reason'] and not closure['had_unresolved_deadline'] and
                        not state['evidence_io_loss'] and state['worker_key'] is not None and
                        not state['outer_hit'] and wall <= 960 and worker_reap['elapsed_s'] <= 900 and
                        worker_reap['returncode'] == 0 and closure['samples_taken'] > 0 and
                        peak <= 4294967296 and worker_peak_valid and seal_complete and pins_ok and
                        raw_bytes is not None and raw_bytes <= 1073741824 and
                        shutil.disk_usage(ROOT).free >= 2147483648 and worker is not None and
                        worker['source_generation'] == receipt['source_generation'] and
                        worker['backend_closed'] and worker['secret_store_removed'] and worker['physics_steps'] == 0 and
                        not worker['operation_observer_failure_hashes'] and not worker['accounting_evidence_loss'] and
                        counts['evidence_complete'] and counts['render_exact'] == 14)
                    result = {'source_generation': receipt['source_generation'],
                        'returncode': worker_reap['returncode'], 'reason': closure['reason'],
                        'closure_confirmed': True, 'reaped': True, 'surviving_owned_pids': [],
                        'closure': closure, 'worker': worker, 'counts': counts,
                        'request_counts': request_counts,
                        'child_identity': known.get(state['worker_key'], {}).get('identity'),
                        'seal_complete': seal_complete, 'source_pins_unchanged': pins_ok,
                        'wall_s': wall, 'outer_960s_compliant': not state['outer_hit'] and wall <= 960,
                        'peak_sampled_tree_RSS_bytes': closure['peak_sampled_tree_RSS_bytes'],
                        'wait4_RSS_peaks_bytes': [row['ru_maxrss_bytes'] for row in closure['reaps']],
                        'worker_self_peak_RSS_bytes': worker_peak,
                        'supervisor_self_peak_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                        'measured_peak_RSS_lower_bound_bytes': peak,
                        'resource_semantics': 'Known observed lower bound; finite sampling overshoot, no hard RSS isolation',
                        'raw_bytes': raw_bytes, 'compliant': bool(compliant),
                        'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED'}
                    save(HERE / 'supervisor-result.json', result, exempt=True)
                    post_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
                    post_wall = time.monotonic()-started
                    post_compliant = result['compliant'] and post_peak <= 4294967296 and post_wall <= 960
                    save(HERE / 'receipt-postcheck.json', {'source_generation': receipt['source_generation'],
                        'supervisor_peak_RSS_bytes': post_peak, 'wall_s': post_wall,
                        'compliant': bool(post_compliant)}, exempt=True)
                    result['compliant'] = bool(post_compliant)
                    # Receipt writing is also inside the live outer deadline.
                    if time.monotonic() > state['outer_deadline']:
                        state['outer_hit'] = True
                        save(HERE / 'receipt-deadline-overrun.json', {'status': 'OUTER_DEADLINE',
                            'source_generation': receipt['source_generation'], 'compliant': False,
                            'wall_s': time.monotonic()-started}, exempt=True)
                        result['compliant'] = False
                    print(json.dumps({'returncode': result['returncode'], 'compliant': result['compliant'],
                        'seal_complete': seal_complete, 'source_generation': receipt['source_generation']}), flush=True)
        finally:
            if pid is None or (closure is not None and closure['closure_confirmed']):
                for entry in known.values():
                    os.close(entry['pidfd'])
                signal.setitimer(signal.ITIMER_REAL, 0)
                SUPERVISION = None
                for number, handler in old_handlers.items():
                    signal.signal(number, handler)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                lock.close()
            else:
                # An exceptional cleanup path cannot silently release a live subtree.
                while True:
                    try:
                        closure = supervise(supervisor, pid, known, state,
                            initial_reason='UNRESOLVED_EXCEPTION_LOCK_RETAINED')
                        if closure['closure_confirmed']:
                            save(HERE / 'exception-late-closure.json', {'closure': closure,
                                'compliant': False, 'source_generation': receipt['source_generation']}, exempt=True)
                            for entry in known.values():
                                os.close(entry['pidfd'])
                            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                            lock.close()
                            break
                    except BaseException:
                        time.sleep(1)
    return 0 if result is not None and result['compliant'] else 2


def read_once():
    started = time.monotonic()
    def timeout(signum, frame):
        raise TimeoutError('independent reader wall limit')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    receipt = ready()
    output = ROUND / 'validation/role-probe-reader.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    assert not output.exists() and not (ROUND / 'validation/reader-start.json').exists()
    supervisor = json.loads((HERE / 'supervisor-result.json').read_bytes())
    assert supervisor['source_generation'] == receipt['source_generation']
    assert supervisor['reaped'] and supervisor['closure_confirmed'] and not supervisor['surviving_owned_pids']
    assert supervisor['seal_complete'] and supervisor['outer_960s_compliant']
    assert not any((HERE / name).exists() for name in ('outer-deadline-unresolved.json',
        'seal-incomplete.json', 'late-closure.json', 'exception-late-closure.json', 'receipt-deadline-overrun.json'))
    closure_receipt = json.loads((HERE / 'process-closure.json').read_bytes())
    assert closure_receipt['source_generation'] == receipt['source_generation']
    postcheck = json.loads((HERE / 'receipt-postcheck.json').read_bytes())
    assert postcheck['source_generation'] == receipt['source_generation']
    sealed = json.loads((HERE / 'raw-seal.json').read_bytes())
    assert sealed['status'] == 'COMPLETE' and sealed['source_generation'] == receipt['source_generation']
    before = seal_raw()
    assert before == sealed['files']
    save(ROUND / 'validation/reader-start.json', {'utc': datetime.now(UTC).isoformat(),
        'API': 0, 'render': 0, 'physics': 0, 'source_generation': receipt['source_generation']})
    if not (RAW / 'role-probe-report.json').exists():
        save(output, {'status': 'NOT_RUN_MISSING_FINAL_REPORT', 'reader_calls': 0,
            'source_generation': receipt['source_generation'],
            'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED'})
        signal.alarm(0)
        return 2

    def no_network(event_name, args):
        if event_name.startswith('socket.') or event_name in ('subprocess.Popen', 'os.fork', 'os.system'):
            raise RuntimeError('independent reader forbids network/process')
    sys.addaudithook(no_network)
    from cloud_edge_robot_arm.research.freeze_evidence import verify_role_probe_evidence
    result = verify_role_probe_evidence(RAW)
    elapsed = time.monotonic()-started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    unchanged = seal_raw() == before
    ready()
    assert elapsed <= 180 and peak <= 4294967296 and unchanged
    qualified = (result.get('available') is True and supervisor['compliant'] and
                 postcheck['compliant'] and supervisor['returncode'] == 0)
    save(output, {'status': 'NOMINAL_QUALIFIED' if qualified else 'NOMINAL_NOT_QUALIFIED',
        'reader_calls': 1, 'reader_result': result, 'wall_s': elapsed, 'peak_RSS_bytes': peak,
        'source_generation': receipt['source_generation'],
        'raw_unchanged': unchanged, 'source_pins_unchanged': True,
        'physical_acceptance': False, 'edge_acceptance': False, 'dispatch': False,
        'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED'})
    signal.alarm(0)
    print(json.dumps({'reader_available': result.get('available'), 'nominal_qualified': qualified}), flush=True)
    return 0 if qualified else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight', action='store_true')
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--read', action='store_true')
    args = parser.parse_args()
    try:
        if args.preflight:
            return preflight() or 0
        if args.execute:
            return execute()
        return read_once()
    except BaseException as error:
        # Never expose arbitrary exception text from a credential-bearing process.
        failure = {'mode': 'preflight' if args.preflight else 'execute' if args.execute else 'read',
            'failure_class_sha256': hashlib.sha256(type(error).__name__.encode()).hexdigest(),
            'utc': datetime.now(UTC).isoformat()}
        target = HERE / ('preflight-failure.json' if args.preflight else 'execution-failure.json' if args.execute else 'reader-failure.json')
        if not target.exists():
            save(target, failure)
        print(json.dumps({'status': 'STOPPED', **failure}), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
