"""Read-only verification of the authorized next-round paired-40 actual-model regression."""
from __future__ import annotations

import base64
from collections import Counter
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import sys

from PIL import Image

SOURCE = Path('/home/ningyd/.codex/worktrees/molmo-absence-protocol-1472/BIGsmall')
CHAT = Path('/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu')
sys.path.insert(0, str(SOURCE / 'src'))
from cloud_edge_robot_arm.research.sol_molmo_scenarios import sample_component_scene
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.cloud_vision_fallback import CloudVisionDecision

EXPECTED_COMMIT = '5e68e2f9f1ed7d865f483f41534dec9404c83394'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value):
    return json.loads(json.dumps(value))


def snapshot_frozen_dirs():
    base = CHAT / 'outputs'
    protected = [
        'sol-molmo-observability-40-20261114-v1',
        'geometry-repair-40-20261114-v2',
        'joint-limit-diagnosis-20261114-v2',
        'geometry-repair/host-occlusion-controls',
        'finger-limit-fix-20261114',
    ]
    baseline = read(base / 'next-round-repair-20261114/frozen-dirs-baseline.json')
    counts = {}
    for name in protected:
        root = base / name
        current = {
            str(p.relative_to(root)): digest(p)
            for p in sorted(root.rglob('*'))
            if p.is_file()
        }
        assert current == baseline[name], f'Frozen directory modified: {name}'
        counts[name] = len(current)
    return counts


def request_parts(request):
    message = next(m for m in request['messages'] if m['role'] == 'user')
    if isinstance(message['content'], str):
        return json.loads(message['content']), [
            base64.b64decode(x, validate=True) for x in message.get('images', [])
        ]
    text_parts = [p['text'] for p in message['content'] if p['type'] == 'text']
    assert len(text_parts) == 1
    images = []
    for part in message['content']:
        if part['type'] == 'image_url':
            url = part['image_url']['url']
            assert url.startswith('data:image/png;base64,')
            images.append(base64.b64decode(url.split(',', 1)[1], validate=True))
        else:
            assert part['type'] == 'text'
    return json.loads(text_parts[0]), images


def verify_request(episode, request, entries, evidence):
    assert request['model'] == 'gpt-6.1-sol'
    system = next(m['content'] for m in request['messages'] if m['role'] == 'system')
    payload, images = request_parts(request)
    for forbidden in (
        'component_scene',
        'scene_application',
        'object_position_m',
        'object_yaw_rad',
        'requested_scene',
        'depth_float32_base64',
        'valid_mask_base64',
        'instance_labels',
    ):
        assert forbidden not in json.dumps(payload), forbidden
    if not images:
        assert 'MuJoCo software component diagnostic only' in system
        assert set(payload) == {
            'execution_scope',
            'hardware_dispatch',
            'instruction',
            'geometry',
            'geometry_status',
        }
        assert payload['execution_scope'] == 'MUJOCO_COMPONENT_DIAGNOSTIC'
        assert payload['hardware_dispatch'] is False
        assert payload['geometry_status'] == 'CALIBRATED_DEVELOPMENT_ESTIMATE_NOT_PHYSICAL_ACCEPTANCE'
        return False, None
    assert 'No hardware is dispatched' in system
    assert set(payload) == {
        'instruction',
        'target_phrase',
        'destination_phrase',
        'local_failure',
        'images',
    }
    assert 1 <= len(images) == len(payload['images']) <= 2
    audit = next(
        e['cloud_vision_fallback']
        for e in evidence
        if e.get('cloud_vision_fallback', {}).get('images') == payload['images']
    )
    assert audit['hardware_dispatch'] is False
    assert audit['metric_geometry_source'] == 'FRESH_LOCAL_ORIGINAL_DEPTH_ONLY'
    assert audit['coordinate_system'] == 'normalized_1000_full_original_image'
    assert audit['local_failure'] == payload['local_failure']
    assert audit['image_count'] == len(images)
    for raw, meta in zip(images, payload['images'], strict=True):
        assert hashlib.sha256(raw).hexdigest() == meta['sha256']
        with Image.open(io.BytesIO(raw)) as picture:
            assert picture.size == (meta['width'], meta['height'])
    first = payload['images'][0]
    assert first['role'] == 'FULL_ORIGINAL_RGB'
    assert any(
        e['path'].endswith('/rgb.png') and e['sha256'] == first['sha256'] for e in entries
    )
    matching = []
    for entry in entries:
        if entry['path'].endswith('observation.json'):
            frame = read(episode / entry['path'])
            if frame.get('observation_id') == audit['reference_observation_id']:
                matching.append(frame)
    assert matching
    assert any(
        frame['checksum_sha256'] == audit['reference_checksum']
        and frame['rgb_sha256'] == first['sha256']
        for frame in matching
    )
    if len(images) == 2:
        crop = payload['images'][1]
        assert crop['role'] == 'RGB_CROP_CONTEXT_ONLY'
        x0, y0, x1, y1 = crop['full_image_box_xyxy']
        assert 0 <= x0 < x1 <= first['width'] and 0 <= y0 < y1 <= first['height']
        assert x1 - x0 == crop['width'] <= 97 and y1 - y0 == crop['height'] <= 97
        with (
            Image.open(io.BytesIO(images[0])) as original,
            Image.open(io.BytesIO(images[1])) as part,
        ):
            assert original.crop((x0, y0, x1, y1)).tobytes() == part.tobytes()
    return True, audit


def rescore(episode, result):
    raw = read(episode / 'component/physical-evidence.json')
    samples = []
    for row in raw:
        item = dict(row)
        for name in (
            'object_position_m',
            'object_half_extent_xy_m',
            'region_center_xy_m',
            'region_half_extent_xy_m',
        ):
            item[name] = tuple(item[name])
        for name in ('contact_pairs', 'self_collision_checked_pairs'):
            item[name] = tuple(tuple(pair) for pair in item[name])
        samples.append(PhysicalSample(**item))
    assert samples and samples[0].physics_step == 120
    assert samples[-1].physics_step == result['physics_steps']
    assert all(s.episode_id == result['episode_id'] for s in samples)
    scored = normalized(
        asdict(
            evaluate_evidence(
                samples, CompletionCriteria('object', 'target_region'), evaluation_start_step=120
            )
        )
    )
    assert scored == result['outcome']['independent_physical_outcome']
    return scored


def write_markdown_report(output: Path, report: dict) -> None:
    g = report['groups']
    v1_g = report['v1_groups']
    v2_g = report['v2_groups']
    lines = [
        '# 新一轮真实 Sol+Molmo 40 项配对组件回归报告',
        '',
        f"> 测试代码提交：`{report['tested_source_commit']}`（工作区含已核验的 `tracking.py`、`pose_markers.py`、`sol_molmo_components.py` 修复及在线手指限位守卫；共冻结 `{len(read(CHAT / 'outputs/next-round-repair-20261114/next-40-source-manifest.json')['files'])}` 个源码/配置/模型文件 SHA256，全程零源码漂移、零重试、零硬件下发，未执行 `git push`）。",
        '',
        '## 1. 总览与三轮配对对比',
        '',
        f"- 完整性核对：`{report['integrity_status']}`（40/40 完成，耗时 `{report['wall_time_s']} s`，共校验 `{report['counts']['evidence_files']}` 份证据文件、`{report['counts']['evidence_bytes']}` 字节 SHA256，全部独立物理重算一致）。",
        f"- 冻结历史目录不变：`{sum(report['frozen_file_counts'].values())}` 个受保护历史文件（5 个目录）前/后 SHA256 完全一致。",
        f"- 本轮云端调用：`{report['counts']['cloud_requests']}` 次（其中文本/几何 `{report['counts'].get('text_requests', 0)}` 次、图片回退 `{report['counts'].get('image_requests', 0)}` 次，返回模型 `{report['provider_response_models']}`），Token 用量：`{report['tokens']}`；本地 Molmo 加载 `{report['counts']['model_loads']}` 次、生成 `{report['counts']['local_generations_completed']}/{report['counts']['local_generations']}` 次；执行技能动作 `{report['counts']['executed_actions']}` 个。",
        '',
        '| 分组 | V1 基线 (`sol-molmo-observability-40-v1`) | V2 几何修复 (`geometry-repair-40-v2`) | 本轮 V3 (`next-round-repair-40-v3`) |',
        '| --- | ---: | ---: | ---: |',
    ]
    for split, label in (
        ('fixed', '固定姿态'),
        ('development', 'Development'),
        ('held-out', '原 Held-out'),
    ):
        v1_s = v1_g[split]['physical_success']
        v1_n = v1_g[split]['total']
        v2_s = v2_g[split]['physical_success']
        v2_n = v2_g[split]['total']
        v3_s = g[split]['physical_success']
        v3_n = g[split]['total']
        lines.append(f'| {label} | {v1_s}/{v1_n} | {v2_s}/{v2_n} | {v3_s}/{v3_n} |')
    v1_tot = sum(v1_g[s]['physical_success'] for s in ('fixed', 'development', 'held-out'))
    v2_tot = sum(v2_g[s]['physical_success'] for s in ('fixed', 'development', 'held-out'))
    v3_tot = report['counts']['component_success']
    lines.append(
        f'| 合计 | {v1_tot}/40 ({v1_tot/40*100:.1f}%) | {v2_tot}/40 ({v2_tot/40*100:.1f}%) | {v3_tot}/40 ({v3_tot/40*100:.1f}%) |'
    )
    lines.extend(
        [
            '',
            f"- 相对 V1 的配对状态迁移：`{report['paired_transitions_from_v1']}`",
            f"- 相对 V2 的配对状态迁移：`{report['paired_transitions_from_v2']}`",
            '',
            '## 2. 终止原因与各阶段失败分布',
            '',
            f"- 终止原因分布：`{report['failure_reasons']}`",
            f"- 首阶段（stage 1）失败分布：`{report['first_stage_failure_reasons']}`",
            f"- 末阶段（last stage）失败分布：`{report['last_stage_failure_reasons']}`",
            '',
            '## 3. 逐例配对结果（40 项全量）',
            '',
            '| Case | V1 | V2 | V3 | 物理成功 | 动作数 | 云请求 / 图片回退 | 端点标记 (前/后) | 终止原因 / 首阶段原因 |',
            '| --- | :---: | :---: | :---: | :---: | ---: | :---: | :---: | --- |',
        ]
    )
    v1_map = {p['case']: p['before_component_success'] for p in report['paired_cases_from_v1']}
    v2_map = {p['case']: p['before_component_success'] for p in report['paired_cases_from_v2']}
    for ep in report['episodes']:
        c = ep['case']
        b1 = 'PASS' if v1_map[c] else 'FAIL'
        b2 = 'PASS' if v2_map[c] else 'FAIL'
        b3 = 'PASS' if ep['component_success'] else 'FAIL'
        cloud_col = f"{ep['cloud_requests']} / {'IMG' if ep['image_fallback'] else 'TXT'}"
        mkr = f"{ep['marker_before']}/{ep['marker_after']}"
        reason_col = ep['final_reason'] or '-'
        if not ep['component_success'] and ep['first_stage_reason'] and ep['first_stage_reason'] != ep['final_reason']:
            reason_col = f"{reason_col} ({ep['first_stage_reason']})"
        lines.append(
            f"| `{c}` | {b1} | {b2} | {b3} | `{ep['physical_success']}` | {ep['executed_actions']} | {cloud_col} | `{mkr}` | `{reason_col}` |"
        )
    lines.append('')
    text = '\n'.join(lines)
    (output / 'actual-40-report.md').write_text(text, encoding='utf-8')
    (CHAT / 'outputs/next-round-repair-20261114/actual-40-report.md').write_text(
        text, encoding='utf-8'
    )


def main():
    output = Path(sys.argv[1]).resolve()
    batch, matrix, metadata = [
        read(output / p) for p in ('batch-result.json', 'frozen-matrix.json', 'run-metadata.json')
    ]
    freeze = read(output / 'source-freeze.json')
    original_freeze = CHAT / 'outputs/next-round-repair-20261114/next-40-source-manifest.json'
    assert digest(original_freeze) == metadata['source_freeze_sha256']
    assert read(original_freeze) == freeze
    for name, expected in freeze['files'].items():
        assert digest(Path(name)) == expected, 'Current verifier source drift: ' + name
    assert batch['run_status'] == 'COMPLETED'
    assert batch['completed'] == len(batch['episodes']) == len(matrix) == 40
    assert digest(output / 'frozen-matrix.json') == metadata['matrix_sha256']
    assert metadata['source_commit'] == freeze['source_commit'] == EXPECTED_COMMIT
    assert [(r['split'], r['seed']) for r in batch['episodes']] == [
        (c['split'], c['seed']) for c in matrix
    ]
    assert all(row['cloud_vision_fallback'] is True for row in matrix)
    frozen_file_counts = snapshot_frozen_dirs()

    v1_batch = read(CHAT / 'outputs/sol-molmo-observability-40-20261114-v1/batch-result.json')
    v2_batch = read(CHAT / 'outputs/geometry-repair-40-20261114-v2/batch-result.json')
    v1_prior = {(r['split'], r['seed']): r for r in v1_batch['episodes']}
    v2_prior = {(r['split'], r['seed']): r for r in v2_batch['episodes']}

    counts = Counter()
    reasons = Counter()
    initial = Counter()
    final_gates = Counter()
    response_models = Counter()
    source_variants = set()
    states = []
    rows = []
    fallbacks = []
    pairs_v1 = []
    pairs_v2 = []
    physical_rows = []
    tokens = Counter()

    for row in batch['episodes']:
        episode = output / Path(row['result_path']).parent
        result, assignment, sources = [
            read(episode / p)
            for p in ('result.json', 'scene-assignment.json', 'source-hashes.json')
        ]
        source_variants.add(json.dumps(sources, sort_keys=True))
        for name, expected in sources['files'].items():
            assert freeze['files'][str(SOURCE / name)] == expected, name
        assert result['changed_source_paths'] == []
        assert row['child_returncode'] == 0 and row['process_timed_out'] is False
        entries = read(episode / 'evidence-manifest.json')['files']
        for entry in entries:
            path = (episode / entry['path']).resolve()
            path.relative_to(episode)
            assert path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256'], str(
                path
            )
            counts['evidence_files'] += 1
            counts['evidence_bytes'] += entry['bytes']
        assert result['success'] is False and result['hardware_dispatch'] is False
        assert result['formal_research'] == 'NOT_ACCEPTED' and result['qualified_groups_added'] == 0
        assert result['execution_scope'] == 'MUJOCO_COMPONENT_DIAGNOSTIC'
        assert result['continuous_visibility_proven'] is False
        assert result['cloud_vision_fallback'] is True
        assert 0 <= result['local_generations_completed'] <= result['local_generations'] <= 4
        assert result['model_loads'] == int((episode / 'raw/molmo/loaded.json').is_file())
        completed = list((episode / 'raw/molmo').glob('request-*/generation-completed.json'))
        assert result['local_generations_completed'] == len(completed)
        request_path = episode / 'raw/cloud/request.json'
        assert result['cloud_requests'] == int(request_path.is_file())
        assert 0 <= result['cloud_requests'] <= result['cloud_request_reservations'] <= 1
        for key in (
            'model_loads',
            'local_generations',
            'local_generations_completed',
            'cloud_requests',
            'cloud_request_reservations',
            'executed_actions',
        ):
            counts[key] += result[key]
        stages = [read(p) for p in sorted((episode / 'planning').glob('planning-stage-*.json'))]
        evidence = [
            a['draft']['observation_evidence']
            for s in stages
            for a in s.get('attempts', [])
            if a.get('draft')
        ]
        image = False
        audit = None
        if request_path.exists():
            image, audit = verify_request(episode, read(request_path), entries, evidence)
            response = read(episode / 'raw/cloud/response.json')
            response_models[str(response.get('model'))] += 1
            usage = response.get('usage') or {}
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                tokens[key] += usage.get(key, 0)
            if image:
                counts['image_requests'] += 1
                try:
                    decision = CloudVisionDecision.model_validate_json(
                        response['choices'][0]['message']['content']
                    )
                    action = decision.action
                except (ValueError, KeyError, IndexError, TypeError):
                    action = 'INVALID_RESPONSE'
                counts['image_' + action] += 1
                counts['image_component_success'] += int(bool(result['component_success']))
                fallbacks.append(
                    {
                        'case': episode.name,
                        'original_local_failure': audit['local_failure'],
                        'image_count': audit['image_count'],
                        'response_action': action,
                        'component_success': result['component_success'],
                        'executed_actions': result['executed_actions'],
                        'final_reason': result['outcome'].get('terminal_reason'),
                        'stage_reasons': [s['reason'] for s in stages],
                    }
                )
            else:
                counts['text_requests'] += 1
        outcome = result['outcome']
        assert outcome['native_action_qualification'] == 'UNKNOWN_NOT_GRANTED'
        application = read(episode / 'component/scene-application.json')
        assert application['scope'] == 'OFFLINE_INITIAL_PHYSICS_AUDIT_NOT_ONLINE_MODEL_INPUT'
        if row['split'] == 'fixed':
            assert (
                assignment['scene_sampling'] == 'FIXED_REGISTERED_SCENE'
                and application['requested_scene'] is None
            )
        else:
            expected = sample_component_scene(row['seed'], row['split'])
            assert assignment['component_scene'] == application['requested_scene'] == expected
            assert all(
                abs(a - b) < 1e-10
                for a, b in zip(
                    application['object_position_m'], expected['object_position_m'], strict=True
                )
            )
            yaw = expected['object_yaw_rad']
            q = [math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]
            assert all(
                abs(a - b) < 1e-10
                for a, b in zip(application['object_quaternion_wxyz'], q, strict=True)
            )
            states.append(
                (tuple(application['object_position_m']), tuple(application['object_quaternion_wxyz']))
            )
        scored = rescore(episode, result)
        counts['physical_rescores'] += 1
        counts['safety_violations'] += int(scored['safety_violation'])
        if result['component_success']:
            assert (
                scored['success'] is True
                and result['physical_success'] is True
                and result['executed_actions'] == 8
            )
            counts['component_success'] += 1
            physical_rows.append(
                {
                    'case': episode.name,
                    **{
                        k: scored[k]
                        for k in ('measured_lift_m', 'hold_s', 'placed_stable_s', 'safety_assessment')
                    },
                }
            )
        if result['marker_endpoints_observed']:
            assert all(
                result[k]['status'] == 'OBSERVED' and result[k]['observed_marker_ids'] == [7]
                for k in ('marker_before', 'marker_after')
            )
            counts['marker_endpoints_observed'] += 1
        first = stages[0]['reason'] if stages else None
        last = stages[-1]['reason'] if stages else None
        final = outcome.get('terminal_reason') or result.get('terminal_reason')
        if not result['component_success']:
            reasons[str(final)] += 1
            initial[str(first)] += 1
            if last:
                final_gates[str(last)] += 1
        record = {
            'case': episode.name,
            'seed': row['seed'],
            'split': row['split'],
            'component_success': result['component_success'],
            'physical_success': result['physical_success'],
            'executed_actions': result['executed_actions'],
            'cloud_requests': result['cloud_requests'],
            'image_fallback': image,
            'marker_before': row['marker_before'],
            'marker_after': row['marker_after'],
            'first_stage_reason': first,
            'last_stage_reason': last,
            'final_reason': final,
            'result_path': row['result_path'],
        }
        rows.append(record)
        after = bool(result['component_success'])
        before_v1 = bool(v1_prior[(row['split'], row['seed'])]['component_success'])
        before_v2 = bool(v2_prior[(row['split'], row['seed'])]['component_success'])
        pairs_v1.append(
            {
                'case': episode.name,
                'before_component_success': before_v1,
                'after_component_success': after,
                'transition': ('SUCCESS' if before_v1 else 'FAIL')
                + '->'
                + ('SUCCESS' if after else 'FAIL'),
            }
        )
        pairs_v2.append(
            {
                'case': episode.name,
                'before_component_success': before_v2,
                'after_component_success': after,
                'transition': ('SUCCESS' if before_v2 else 'FAIL')
                + '->'
                + ('SUCCESS' if after else 'FAIL'),
            }
        )
    assert len(source_variants) == 1 and len(states) == len(set(states)) == 30
    assert counts['cloud_request_reservations'] <= 40
    report = {
        'integrity_status': 'PASS',
        'scope': 'PAIRED_40_MUJOCO_COMPONENT_REGRESSION_DISCLOSED_OLD_HELDOUT',
        'tested_source_commit': metadata['source_commit'],
        'completed_episodes': 40,
        'wall_time_s': batch['wall_time_s'],
        'counts': dict(counts),
        'tokens': dict(tokens),
        'amount_returned_by_provider': None,
        'groups': batch['groups'],
        'v1_groups': v1_batch['groups'],
        'v2_groups': v2_batch['groups'],
        'frozen_file_counts': frozen_file_counts,
        'failure_reasons': dict(reasons),
        'first_stage_failure_reasons': dict(initial),
        'last_stage_failure_reasons': dict(final_gates),
        'provider_response_models': dict(response_models),
        'image_fallback_episodes': fallbacks,
        'paired_transitions_from_v1': dict(Counter(p['transition'] for p in pairs_v1)),
        'paired_transitions_from_v2': dict(Counter(p['transition'] for p in pairs_v2)),
        'paired_cases_from_v1': pairs_v1,
        'paired_cases_from_v2': pairs_v2,
        'episodes': rows,
        'successful_physical_measurements': physical_rows,
        'source_snapshot_variants': 1,
        'distinct_varied_states': 30,
        'process_timeouts': 0,
        'raw_integrity': 'All episode manifest sizes and SHA256 verified',
        'physical_rescore': 'Exact rescore of all recorded physical samples with unchanged CompletionCriteria',
        'cloud_scope': 'Exact text or image schema, no raw depth/instance/initial physics truth; original RGB and crop hashes/pixels verified',
        'hardware_dispatch': False,
        'formal_research': 'NOT_ACCEPTED',
        'native_action_qualification': 'UNKNOWN_NOT_GRANTED',
        'qualified_groups_added': 0,
        'continuous_marker_visibility_proven': False,
        'qualification_limit': 'Disclosed paired component regression; not unseen generalization or formal/hardware acceptance',
    }
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    write_markdown_report(output, report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    'integrity_status',
                    'completed_episodes',
                    'counts',
                    'tokens',
                    'failure_reasons',
                    'paired_transitions_from_v1',
                    'paired_transitions_from_v2',
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == '__main__':
    main()
