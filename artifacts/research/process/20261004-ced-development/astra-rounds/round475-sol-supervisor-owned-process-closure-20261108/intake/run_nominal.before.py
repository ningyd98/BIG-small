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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


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
        if path.is_symlink():
            raise ValueError('symlink in owned output')
        if path.is_file():
            total += path.stat().st_size
    return total


def pins():
    assert sha(ROUND / 'plan.json') == PLAN_SHA
    for row in PLAN['inputs'] + json.loads((ROUND / 'source-pins.json').read_bytes()):
        path = ROOT / row['path']
        assert path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256'], row['path']


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
    lines = path.read_bytes().splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith(b'\n')]


def operation_counts(rows):
    operations = [row for row in rows if row['event'] == 'BACKEND_OPERATION']
    captures = {row['operation_id']: row for row in operations
                if row['kind'] == 'CAPTURE' and row['phase'] == 'BEGIN'}
    ends = {row['operation_id']: row for row in operations
            if row['kind'] == 'CAPTURE' and row['phase'] == 'END'}
    complete = [ends[key] for key in captures if key in ends and
                ends[key]['error_type'] is None and ends[key]['pass_count'] in (2, 3)]
    uncertain = [row for key, row in captures.items() if key not in ends or
                 ends[key]['error_type'] is not None or ends[key]['pass_count'] not in (2, 3)]
    lower = sum(row['pass_count'] for row in complete)
    return {'reset_invoked': sum(row['kind'] == 'RESET' and row['phase'] == 'BEGIN'
                                 for row in operations),
            'captures_invoked': len(captures), 'captures_completed': len(complete),
            'implicit_captures_invoked': sum(row['capture_context'] == 'RESET' for row in captures.values()),
            'explicit_captures_invoked': sum(row['capture_context'] == 'EXPLICIT' for row in captures.values()),
            'render_completed_lower_bound': lower,
            'render_upper_bound': lower + sum(2 if row['capture_context'] == 'RESET' else 3
                                              for row in uncertain),
            'render_exact': lower if not uncertain else None,
            'capture_unknown_intervals': len(uncertain),
            'forbidden_operation_count': sum(row['kind'] in ('CONTROL', 'PHYSICS', 'COMMAND')
                                              for row in operations)}


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

    def observe(boundary):
        result = boundary.result or {}
        sensor = result.get('sensor_frame') or {}
        hashes = tuple(result.get('pass_state_hashes') or ())
        event('BACKEND_OPERATION', operation_id=boundary.operation_id, kind=boundary.kind,
              phase=boundary.phase, episode_id=boundary.episode_id,
              physics_step=boundary.physics_step, sim_time_s=boundary.sim_time_s,
              error_type=boundary.error_type, capture_context=context['capture'],
              frame_id=sensor.get('frame_id'), pass_count=len(hashes), pass_state_hashes=list(hashes))

    def check():
        ready()
        checkpoint(admitted_at, binding.planner, binding.settings)
        assert backend.total_physics_steps == 0 and not backend.operation_observer_failures
        counts = operation_counts(journal())
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
            backend.reset(PhysicalScenarioConfig.scenario('S01_NORMAL_STATIC', seed=0))
            check()
            with MuJoCoCaptureSession(simulator, backend=backend) as session:
                for index in range(4):
                    check()
                    context['capture'] = 'EXPLICIT'
                    event('CAPTURE_BOUNDARY', index=index)
                    frame = session.capture_with_instances()
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
            counts = operation_counts(journal())
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
            physics_steps = backend.total_physics_steps
            # Error details can contain arbitrary strings; persist only safe classes/digests.
            operation_failures = [digest(dict(row)) for row in backend.operation_observer_failures]
            try:
                event('SHUTDOWN_BEGIN')
                backend.shutdown()
                closed = True
                event('SHUTDOWN_END')
            except BaseException as error:
                report.update(status='BLOCKED', shutdown_failure_class_sha256=digest(type(error).__name__))
        report.update(finished_at=datetime.now(UTC).isoformat(),
            unexecuted_attempt_count=4-len(report['attempts']))
        safe_report = probe._safe_attempt_record(report, key)
        if binding is not None:
            binding.store.delete_secret(binding.profile.profile_id)
            assert not binding.store.has_secret(binding.profile.profile_id)
            binding.planner._api_key = ''
        key = ''
        binding = None
        event('SECRET_REMOVED_FROM_STORE')
    checksum = probe._write(RAW / 'role-probe-report.json', safe_report)
    with (RAW / 'role-probe-report.sha256').open('x') as stream:
        stream.write(checksum + '\n')
    if safe_report.get('status') == 'PASS':
        probe._write(RAW / 'roles-frozen.json', safe_report['bundle'])
    save(RAW / 'worker-result.json', {'status': safe_report.get('status'),
        'initialized': initialized, 'backend_closed': closed, 'secret_store_removed': True,
        'physics_steps': physics_steps, 'operation_observer_failure_hashes': operation_failures,
        'counts': operation_counts(journal()), 'fresh_frames': observed_frames,
        'completion_tokens_from_successful_gate_checks': completion_tokens,
        'elapsed_s': time.monotonic()-admitted_at,
        'peak_self_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024})
    event('WORKER_COMPLETE', status=safe_report.get('status'))
    return 0 if safe_report.get('status') == 'PASS' else 2


def process_identity(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')')+2:].split()
        pages = Path(f'/proc/{pid}/statm').read_text().split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
            'starttime': int(fields[19]), 'rss_bytes': int(pages[1])*os.sysconf('SC_PAGE_SIZE')}


def owned_tree(identity, known):
    # Only the known worker's ancestry is traversed; never scan unrelated /proc records.
    todo = [identity['pid']]
    current = []
    visited = set()
    while todo:
        pid = todo.pop()
        if pid in visited:
            continue
        visited.add(pid)
        row = process_identity(pid)
        if row is None:
            continue
        if pid in known:
            assert row['starttime'] == known[pid]['starttime']
        else:
            assert row['ppid'] in visited
            known[pid] = row
        current.append(row)
        # This is an own-descendant PID index, containing no argv/env/credential data.
        for task in Path(f'/proc/{pid}/task').iterdir():
            try:
                todo.extend(int(child) for child in (task / 'children').read_text().split())
            except (FileNotFoundError, ProcessLookupError):
                continue
    return current


def seal_raw():
    return [{'path': str(path.relative_to(RAW)), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(RAW.rglob('*')) if path.is_file()]


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


def execute():
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
    pid = None
    identity = None
    known = {}
    reaped = False
    status = None
    usage = None
    reason = None
    started = None
    peak_rss = 0
    max_interval = 0.0
    last_sample = None
    cancelled = {'signal': None}
    old_handlers = {}
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
        started = time.monotonic()
        RAW.mkdir(parents=True)
        save(HERE / 'execution-start.json', {'utc': datetime.now(UTC).isoformat(),
            'source_generation': receipt['source_generation'], 'runner_sha256': sha(Path(__file__)),
            'planned_attempt_count': 4, 'admitted_monotonic': started})
        # Adopt unexpected descendants on Linux so cleanup can reap them as well.
        assert ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, lambda number, frame: cancelled.update(signal=number))
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                lock.close()  # Parent owns the serialization lock through exit/reap.
                stdout = os.open(RAW / 'worker.stdout', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                stderr = os.open(RAW / 'worker.stderr', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.dup2(stdout, 1)
                os.dup2(stderr, 2)
                os.close(stdout)
                os.close(stderr)
                code = execute_child(key, started)
            except BaseException as error:
                key = ''
                event('WORKER_OUTER_FAILURE', failure_class_sha256=digest(type(error).__name__))
                code = 2
            os._exit(code)
        key = ''
        identity = process_identity(pid)
        assert identity is not None
        known[pid] = identity
        with (HERE / 'resource-samples.jsonl').open('x') as samples:
            while True:
                current = time.monotonic()
                if last_sample is not None:
                    max_interval = max(max_interval, current-last_sample)
                last_sample = current
                found, child_status, child_usage = os.wait4(pid, os.WNOHANG)
                if found:
                    status, usage, reaped = child_status, child_usage, True
                    break
                tree = owned_tree(identity, known)
                rss = sum(row['rss_bytes'] for row in tree if row['state'] != 'Z')
                peak_rss = max(peak_rss, rss)
                raw_bytes = size(RAW)
                free = shutil.disk_usage(ROOT).free
                rows = journal()
                begun = [row for row in rows if row['event'] == 'ATTEMPT_BEGIN']
                returned = {row['index'] for row in rows if row['event'] == 'ATTEMPT_RETURNED'}
                inflight = [row for row in begun if row['index'] not in returned]
                sample = {'monotonic': current, 'wall_s': current-started, 'tree': tree,
                    'rss_bytes': rss, 'raw_bytes': raw_bytes, 'disk_free_bytes': free,
                    'inflight_attempt_indices': [row['index'] for row in inflight]}
                samples.write(json.dumps(sample)+'\n')
                samples.flush()
                if cancelled['signal']:
                    reason = 'CANCELLED_SIGNAL'
                elif current-started >= 900:
                    reason = 'CHILD_WALL_BUDGET'
                elif rss > 4294967296 or raw_bytes > 1073741824 or free < 2147483648:
                    reason = 'RESOURCE_BUDGET'
                elif len(tree) != 1:
                    reason = 'UNEXPECTED_DESCENDANT'
                elif any(current-row['monotonic'] > 185 for row in inflight):
                    reason = 'REQUEST_WATCHDOG'
                if reason:
                    break
                time.sleep(0.2)
    except BaseException as error:
        reason = 'SUPERVISOR_FAILURE_' + hashlib.sha256(type(error).__name__.encode()).hexdigest()
    finally:
        key = ''
        try:
            # Recheck identities before signaling only this owned process group/tree.
            if pid is not None and not reaped:
                live = process_identity(pid)
                if identity is None and live is not None:
                    identity = live
                    known[pid] = live
                if live is not None and identity and live['starttime'] == identity['starttime']:
                    if live['pgrp'] == pid:
                        os.killpg(pid, signal.SIGTERM)
                    else:
                        os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic()+2
                while time.monotonic() < deadline:
                    found, child_status, child_usage = os.wait4(pid, os.WNOHANG)
                    if found:
                        status, usage, reaped = child_status, child_usage, True
                        break
                    time.sleep(0.05)
                if not reaped:
                    live = process_identity(pid)
                    if live is not None and identity and live['starttime'] == identity['starttime']:
                        if live['pgrp'] == pid:
                            os.killpg(pid, signal.SIGKILL)
                        else:
                            os.kill(pid, signal.SIGKILL)
                    _, status, usage = os.wait4(pid, 0)
                    reaped = True
            survivors = []
            for child_pid, old in known.items():
                if child_pid == pid:
                    continue
                live = process_identity(child_pid)
                if live is not None and live['starttime'] == old['starttime']:
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        os.wait4(child_pid, 0)
                    except ChildProcessError:
                        pass
                    if process_identity(child_pid) is not None:
                        survivors.append(child_pid)
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)
            if started is not None:
                rows = journal()
                final_pins = True
                try:
                    ready()
                except BaseException:
                    final_pins = False
                worker_result = RAW / 'worker-result.json'
                worker = json.loads(worker_result.read_bytes()) if worker_result.exists() else None
                begun = [row for row in rows if row['event'] == 'ATTEMPT_BEGIN']
                returned = [row for row in rows if row['event'] == 'ATTEMPT_RETURNED']
                attempts = []
                for path in sorted(RAW.glob('attempt-*/attempt.json')):
                    attempts.append(json.loads(path.read_bytes()))
                costs = [cost for attempt in attempts for cost in attempt.get('cost_ledger', {}).get('requests', [])]
                raw_bytes = size(RAW)
                wall = time.monotonic()-started
                compliant = (not reason and reaped and not survivors and final_pins and wall <= 900 and
                    peak_rss <= 4294967296 and raw_bytes <= 1073741824 and
                    shutil.disk_usage(ROOT).free >= 2147483648 and worker is not None and
                    worker['backend_closed'] and worker['secret_store_removed'] and worker['physics_steps'] == 0 and
                    not worker['operation_observer_failure_hashes'])
                result = {'returncode': os.waitstatus_to_exitcode(status) if status is not None else None,
                    'reason': reason, 'child_identity': identity, 'owned_process_identities': list(known.values()),
                    'reaped': reaped, 'surviving_owned_pids': survivors, 'wall_s': wall,
                    'outer_960s_compliant': wall <= 960, 'peak_sampled_tree_RSS_bytes': peak_rss,
                    'wait4_child_maxrss_bytes': usage.ru_maxrss*1024 if usage is not None else None,
                    'maximum_sampling_interval_s': max_interval,
                    'resource_semantics': 'Abort thresholds with finite sampling overshoot; not hard isolation',
                    'raw_bytes': raw_bytes, 'source_pins_unchanged': final_pins,
                    'compliant': compliant, 'worker': worker, 'counts': operation_counts(rows),
                    'attempts_started': len(begun), 'attempts_returned': len(returned),
                    'sent_at_known_requests': sum(cost.get('sent_at') is not None for cost in costs),
                    'settled_requests': sum(cost.get('finished_at') is not None for cost in costs),
                    'inflight_attempts_unknown': len(begun)-len(returned),
                    'planned_attempt_count': 4, 'unexecuted_returned_attempt_denominator': 4-len(returned),
                    'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED'}
                save(HERE / 'supervisor-result.json', result)
                save(HERE / 'raw-seal.json', {'files': seal_raw(), 'raw_root': str(RAW),
                     'mutation_policy': 'Original local-only raw; manifest is not full remote reproduction package'})
                print(json.dumps({'returncode': result['returncode'], 'compliant': compliant,
                    'attempts_returned': len(returned), 'sent_at_known_requests': result['sent_at_known_requests'],
                    'inflight_attempts_unknown': result['inflight_attempts_unknown']}), flush=True)
            elif reason:
                save(HERE / 'admission-stopped.json', {'reason': reason, 'workload_started': False,
                    'API': 0, 'render': 0, 'physics': 0})
                print('RESOURCE_ADMISSION_STOPPED: no workload launched; inspect saved nonsecret evidence', flush=True)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
    if pid is None or status is None:
        return 2
    return 0 if os.waitstatus_to_exitcode(status) == 0 and compliant else 2


def read_once():
    ready()
    output = ROUND / 'validation/role-probe-reader.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    assert not output.exists() and not (ROUND / 'validation/reader-start.json').exists()
    supervisor = json.loads((HERE / 'supervisor-result.json').read_bytes())
    assert supervisor['reaped'] and not supervisor['surviving_owned_pids']
    if supervisor['child_identity']:
        assert process_identity(supervisor['child_identity']['pid']) is None
    before = seal_raw()
    assert before == json.loads((HERE / 'raw-seal.json').read_bytes())['files']
    save(ROUND / 'validation/reader-start.json', {'utc': datetime.now(UTC).isoformat(),
        'API': 0, 'render': 0, 'physics': 0})
    if not (RAW / 'role-probe-report.json').exists():
        save(output, {'status': 'NOT_RUN_MISSING_FINAL_REPORT', 'reader_calls': 0,
            'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED'})
        return 2
    started = time.monotonic()

    def timeout(signum, frame):
        raise TimeoutError('independent reader wall limit')

    def no_network(event_name, args):
        if event_name.startswith('socket.') or event_name in ('subprocess.Popen', 'os.fork', 'os.system'):
            raise RuntimeError('independent reader forbids network/process')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(180)
    sys.addaudithook(no_network)
    from cloud_edge_robot_arm.research.freeze_evidence import verify_role_probe_evidence
    result = verify_role_probe_evidence(RAW)
    elapsed = time.monotonic()-started
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    unchanged = seal_raw() == before
    ready()
    assert elapsed <= 180 and peak <= 4294967296 and unchanged
    qualified = result.get('available') is True and supervisor['compliant'] and supervisor['returncode'] == 0
    save(output, {'status': 'NOMINAL_QUALIFIED' if qualified else 'NOMINAL_NOT_QUALIFIED',
        'reader_calls': 1, 'reader_result': result, 'wall_s': elapsed, 'peak_RSS_bytes': peak,
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
