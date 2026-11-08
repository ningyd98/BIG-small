"""R471 fixed offline diagnosis. Frozen pixels only; no engine or repair."""

import argparse
import base64
import hashlib
import io
import json
import math
import re
import resource
import shutil
import signal
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
ROUND = Path(__file__).resolve().parents[1]
PLAN_SHA = '1f9f533c2270cfd8082409421968909ac3ee7386e9271d735e8d8c425b2084c2'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False,
                  default=lambda value: value.isoformat() if isinstance(value, datetime) else None)
        stream.write('\n')


def verify(plan):
    for row in plan['input_pins']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    current = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / 'src/cloud_edge_robot_arm').rglob('*.py')}
    for name in ('configs/research/native_operational_calibration.yaml',
                 'assets/robots/franka_panda/scene.xml',
                 'assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml',
                 'scripts/collect_native_calibration.py', 'pyproject.toml'):
        current[name] = sha(ROOT / name)
    assert current == plan['source_hashes']


def safe_blob(root, name):
    relative = Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    path = root / relative
    assert path.is_file() and not any(p.is_symlink() for p in (path, *path.parents))
    assert path.resolve().is_relative_to(root.resolve())
    return path


def main(plan_path, output):
    assert plan_path == ROUND / 'plan.json' and sha(plan_path) == PLAN_SHA
    plan = json.loads(plan_path.read_bytes())
    spec = plan['diagnostic']
    assert output == Path(spec['argv'][-1]) and not output.exists()
    verify(plan)
    frozen = json.loads((ROUND / 'implementation/frozen-invocation.json').read_bytes())
    assert frozen['runner_sha256'] == sha(Path(__file__))
    output.mkdir(parents=True)
    started = time.monotonic()
    save(output / 'started.json', {'utc': datetime.now(UTC), 'monotonic': started,
                                 'plan_sha256': PLAN_SHA, 'runner_sha256': sha(Path(__file__)),
                                 'scope': 'OFFLINE_DIAGNOSTIC_ONLY', 'new_actual_attempts': 0})

    def deadline(signum, frame):
        raise TimeoutError('offline wall budget')

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(120)

    def budget():
        assert time.monotonic() - started <= 120
        assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 <= 2147483648
        assert shutil.disk_usage(ROOT).free >= 1073741824
        assert sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) <= 268435456

    def guard(event, args):
        if event == 'import':
            name = args[0]
            simulation = 'cloud_edge_robot_arm.simulation'
            forbidden = ('mujoco', 'torch', 'cloud_edge_robot_arm.simulation_runtime',
                         'cloud_edge_robot_arm.cloud', 'cloud_edge_robot_arm.simulation_runtime_adapter')
            if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden):
                raise RuntimeError('forbidden diagnostic import: ' + name)
            if name.startswith(simulation + '.') and name != simulation + '.models':
                raise RuntimeError('forbidden simulation import: ' + name)
            if name.startswith('cloud_edge_robot_arm.research.'):
                raise RuntimeError('full research reader/application imports forbidden')
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.posix_spawn'):
            raise RuntimeError('network/process action forbidden in offline diagnosis')

    sys.addaudithook(guard)
    import cv2
    import numpy as np
    import PIL
    from PIL import Image
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

    cv2.ocl.setUseOpenCL(False)
    cv2.setNumThreads(1)
    protocol_path = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds/round470-teacher-monitor-transient-file-race-20261108/actual/protocol/protocol.json'
    protocol = json.loads(protocol_path.read_bytes())
    registration = PoseMarkerRegistration(**protocol['geometry']['pose_marker'])
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    parameters.errorCorrectionRate = 0.0
    parameter_values = {name: getattr(parameters, name) for name in dir(parameters)
                        if not name.startswith('_') and type(getattr(parameters, name)) in (bool, int, float, str)}
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    results = []
    raw_hashes = {}

    def quads(values):
        rows = []
        for value in values:
            points = np.asarray(value, dtype=float).reshape(4, 2)
            rows.append({'corners_px': points.tolist(),
                         'side_lengths_px': np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1).tolist(),
                         'bbox_px': [float(points[:, 0].min()), float(points[:, 1].min()),
                                     float(points[:, 0].max()), float(points[:, 1].max())]})
        return rows

    for spec_frame in spec['frames']:
        budget()
        metadata_path = Path(spec_frame['metadata'])
        metadata = json.loads(metadata_path.read_bytes())
        raw_hashes[str(metadata_path)] = sha(metadata_path)
        assert metadata['capture_source'] == spec_frame['capture_source']
        assert metadata['pass_count'] == spec_frame['pass_count']
        root = metadata_path.parents[2]
        frame = json.loads(json.dumps(metadata['frame']))
        payload = frame['observation_payload']
        for field, name in metadata['encoded_fields'].items():
            assert field in ('rgb_png_base64', 'depth_float32_base64', 'valid_mask_base64') and field not in payload
            path = safe_blob(root, name)
            value = base64.b64encode(path.read_bytes()).decode()
            assert hashlib.sha256(value.encode()).hexdigest() == metadata['encoded_string_sha256'][field]
            payload[field] = value
            raw_hashes[str(path)] = sha(path)
        assert digest(payload) == metadata['observation_payload_sha256']
        for name, checksum in frame['file_hashes'].items():
            path = safe_blob(root, name)
            assert sha(path) == checksum
            raw_hashes[str(path)] = checksum
        observation = RGBDObservation.model_validate(payload)
        assert observation.model_dump(mode='json') == payload
        # Only the unchanged observation and known registration enter production detection.
        estimate = detect_pose_marker(observation, registration)
        png = Path(spec_frame['rgb']).read_bytes()
        assert png == base64.b64decode(observation.rgb_png_base64, validate=True)
        rgb = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        accepted, ids, rejected = detector.detectMarkers(gray)
        result = {'acquisition': spec_frame['acquisition'], 'metadata_sha256': sha(metadata_path),
                  'rgb_sha256': hashlib.sha256(png).hexdigest(), 'observation_checksum': observation.checksum_sha256,
                  'captured_at': observation.captured_at, 'production_estimate': asdict(estimate),
                  'same_original_gray': {'shape': list(gray.shape), 'min': int(gray.min()), 'max': int(gray.max()),
                       'ids': None if ids is None else ids.reshape(-1).tolist(),
                       'accepted': quads(accepted), 'rejected': quads(rejected)}}
        results.append(result)
        with (output / (spec_frame['acquisition'] + '-original-rgb.png')).open('xb') as stream:
            stream.write(png)
        if spec_frame['acquisition'] == 'acquisition-123':
            assert estimate.status == 'UNKNOWN' and estimate.reason == 'known_marker_not_observed'
            crop = Image.fromarray(rgb).crop((184, 108, 210, 134))
            crop.save(output / 'diagnostic-crop-123.png')
            crop.resize((208, 208), Image.Resampling.NEAREST).save(output / 'diagnostic-crop-123-nearest8x.png')
            save(output / 'diagnostic-crop-123-pixels.json', {
                'scope': 'DIAGNOSTIC_DERIVATIVE_NEVER_DETECTOR_INPUT',
                'source_sha256': hashlib.sha256(png).hexdigest(), 'crop_xyxy': [184, 108, 210, 134],
                'nearest_scale': 8, 'gray_original_values': gray[108:134, 184:210].tolist(),
                'selection': 'Fixed human-inspected display crop; no XML or physics projection used for detector.'})
        save(output / (spec_frame['acquisition'] + '-detector.json'), result)
        budget()

    asset = ROOT / 'assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml'
    tree = ET.fromstring(asset.read_bytes())
    cells = []
    bits = np.zeros((6, 6), dtype=np.uint8)
    quiet = None
    for geom in tree.findall("./worldbody/body[@name='object']/geom"):
        name = geom.get('name', '')
        if name == 'pose_marker_outboard_v3_quiet':
            quiet = dict(geom.attrib)
        match = re.fullmatch(r'pose_marker_outboard_v3_r([0-5])c([0-5])', name)
        if match:
            row, col = map(int, match.groups())
            rgba = [float(v) for v in geom.get('rgba').split()]
            assert rgba[0] == rgba[1] == rgba[2] and rgba[0] in (0.01, 0.98)
            bits[row, col] = 255 if rgba[0] == 0.98 else 0
            cells.append({'row': row, 'column': col, **dict(geom.attrib)})
    assert len(cells) == 36 and quiet is not None
    xs = sorted({float(cell['pos'].split()[0]) for cell in cells})
    ys = sorted({float(cell['pos'].split()[1]) for cell in cells}, reverse=True)
    assert len(xs) == len(ys) == 6
    position_order_equal = all(
        xs.index(float(cell['pos'].split()[0])) == cell['column']
        and ys.index(float(cell['pos'].split()[1])) == cell['row']
        for cell in cells)
    expected = cv2.aruco.generateImageMarker(dictionary, 7, 6)
    reference = np.pad(np.repeat(np.repeat(expected, 20, axis=0), 20, axis=1), 20,
                       mode='constant', constant_values=255)
    ref_corners, ref_ids, ref_rejected = detector.detectMarkers(reference)
    Image.fromarray(reference).save(output / 'synthetic-id7-reference-only.png')
    static = {'scope': 'STATIC_XML_AND_SYNTHETIC_REFERENCE_ONLY', 'asset_sha256': sha(asset),
              'cells': cells, 'quiet': quiet, 'XML_bits_6x6': bits.tolist(),
              'dictionary_bits_6x6': expected.tolist(),
              'grid_positions_order_equal': position_order_equal,
              'grid_x_centers_m': xs, 'grid_y_centers_m_descending': ys,
              'pattern_equal': bool(np.array_equal(bits, expected)) and position_order_equal,
              'reference': {'shape': list(reference.shape), 'ids': None if ref_ids is None else ref_ids.reshape(-1).tolist(),
                            'accepted': quads(ref_corners), 'rejected': quads(ref_rejected)},
              'boundary': 'XML equality and synthetic decoding do not prove actual-frame visibility or rasterization.'}
    save(output / 'xml-and-reference.json', static)
    verify(plan)
    for name, checksum in raw_hashes.items():
        assert sha(Path(name)) == checksum
    summary = {'status': 'OFFLINE_DIAGNOSIS_COMPLETE', 'root_status': 'PIXEL_DECODER_STAGE_LOCALIZED_REPAIR_UNRESOLVED',
               'versions': {'cv2': cv2.__version__, 'numpy': np.__version__, 'Pillow': PIL.__version__},
               'detector_parameters': parameter_values, 'results': results,
               'XML_pattern_equal': static['pattern_equal'], 'synthetic_reference_ids': static['reference']['ids'],
               'hypotheses': {'asset_dictionary_bits': 'REFUTED_AS_STATIC_BIT_MISMATCH' if static['pattern_equal'] else 'SUPPORTED_STATIC_BIT_MISMATCH',
                   'decoder_unavailable': 'REFUTED_BY_SYNTHETIC_ID7' if static['reference']['ids'] == [7] else 'UNRESOLVED',
                   'sampling_aliasing_quiet_border_rasterization': 'UNRESOLVED_REQUIRES_NEXT_ASTRA',
                   'lighting_occlusion_or_specific_parameter_behavior': 'UNRESOLVED'},
               'source_and_selected_raw_unchanged': True, 'selected_raw_sha256': raw_hashes,
               'calls': {'production_detector': 4, 'same_original_gray_OpenCV': 4, 'synthetic_reference_OpenCV': 1},
               'this_round': {'new_actual_attempts': 0, 'API': 0, 'physics': 0, 'render': 0},
               'prior_actual_attempts': 2, 'native': 'UNKNOWN', 'formal': 'NOT_ACCEPTED',
               'wall_s': time.monotonic() - started,
               'peak_RSS_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
               'next': 'Actual Astra required before repair or expanded diagnosis; no third actual authorized.'}
    save(output / 'summary.json', summary)
    budget()
    signal.alarm(0)
    print(json.dumps({'status': summary['status'], 'production_statuses': [row['production_estimate']['reason'] for row in results],
                      'XML_pattern_equal': static['pattern_equal'], 'reference_ids': static['reference']['ids'],
                      'wall_s': summary['wall_s']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.plan, args.output)
