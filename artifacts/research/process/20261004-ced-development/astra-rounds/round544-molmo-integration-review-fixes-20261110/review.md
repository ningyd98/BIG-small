# R544 independent integration review

Actual reviewer/planner: `gpt-6-astra`. Reviewed base `025c538935199ea7d3aa8cf15b6e93ac9826cf3a` to committed HEAD `31b2ee98a9fb036b36afdb784ef162b772307202`, plus the two explicitly supplied untracked Task 4 files. All eight input bytes/SHA256 values matched. AGENTS.md, spec and R542/R543 plans read. No source, index, branch, model, dependency, service, GPU, network or hardware changes/calls made.

Assessment: **fix Important findings before claiming integration ready**. Critical: none established. Important: five below. Minor: intentional CLI bootstrap creates seven E402 findings (lines 24–38); minimum scoped lint annotation is approved in the plan. No other minor cleanup is requested.

Strengths: exact full-match native point grammar rejects duplicated tags, malformed attributes, wrong image IDs and nonfinite/overflow values; provider bindings include observation/RGB/query hashes and raw reparse; elapsed-time checks follow local and cloud calls; geometry extraction preserves legacy templates and calibration limits; OpenCV refuses unsupported camera/support evidence; cloud extra fields and skill ordering are constrained; factory preserves the selected Sol route and default payment refusal. Tests exercise the real pipeline with explicit CPU boundary fixtures. Existing model-load failure fallback correctly counts the saved load-started record: this is not a zero-count bug.

## I1 — Important: Request binding is checked only at entry

Location: `src/cloud_edge_robot_arm/vision/grounded_planner.py:89-94, 128-132, 255-270`.

Replacing request.observation during fixture cloud reply yields PLANNED although request/evidence checksums differ. Changing user_instruction during reply yields PLANNED with blue-cylinder instruction and red-block task target. Root cause: _fresh checks the cached observation and cloud settings; mutable request/task context is reread without comparing its initial identity.

## I2 — Important: Duplicate JSON skills silently replace refusal

Location: `src/cloud_edge_robot_arm/vision/grounded_planner.py:264-270`.

Raw {"skills":[],"skills":[valid required sequence]} produces PLANNED. Root cause: Pydantic model_validate_json accepts duplicate object keys using last-wins parsing before strict field validation.

## I3 — Important: Paid cloud failure is reported as passing diagnostic

Location: `scripts/probe_molmo_grounded_planner.py:320-349`.

CPU native fixture + real transport boundary mocked to timeout: paid_starts=1, pipeline=PLANNER_FAILED, exit=0, diagnostic_passed=true. Root cause: Native success predicate always uses geometry readiness, even when --allow-paid requests cloud integration.

## I4 — Important: Run evidence loses inputs, cloud bodies and failure manifests

Location: `scripts/probe_molmo_grounded_planner.py:222-227, 288-310, 321-330, 350-364, 380-396`.

Normal-input paid timeout run retains no cloud request body; observer discards RESPONSE bodies entirely; PlannerDraft.raw_text is omitted from saved report/raw. Failed-load fixture counts one load correctly but writes no raw-manifest.local.json. Factory role snapshot/source hashes are not emitted by grounded_planner.py:112-125. Root cause: Raw capture is restricted to --capture-fresh and native provider files; the CLI observer only counts hashes and manifest creation exists only on the success path.

## I5 — Important: A decoding failure erases completed generation output and count

Location: `src/cloud_edge_robot_arm/vision/molmo_pointing.py:317-330`.

Mock generate returns token IDs then tokenizer.decode raises: generation_calls_started=1, generation_calls_completed=0, no output-token-ids.json, failure.json exists. Root cause: Token persistence and completed counter occur after decoding/parsing rather than immediately after successful generation.

The five required focus classes were assessed: native parsing and geometry refusal are supported by inspected code/tests; late replies fail freshness but request replacement is I1; extra cloud fields fail but duplicate keys are I2; replay/native labels are explicit but end-to-end status and evidence persistence need I3–I5. Mutation of cloud timeout is already rejected; immutable generation-parameter mappings and Sol route checks remain sound. Factory profile lookup does not activate a profile. Legacy extraction changed no calibrated thresholds or templates; no legacy functional regression established.

Verification: independent CPU run of `tests/test_molmo_pointing.py tests/test_molmo_grounded_planner.py tests/test_molmo_grounded_cli.py -q -p no:cacheprovider` passed **100 tests in 1.01s**. Parent reports broader 220 PASS, not rerun here. An initial Ruff invocation could not create its read-only worktree cache; rerunning with `--no-cache` produced the known seven E402 findings. This is an environment/cache write restriction, not a new source failure. Reproduction scripts do not invoke actual models, paid APIs, GPUs or hardware; no model/dependency assets were read/modified by inference.

Declined to judge: actual native accuracy, BF16 runtime operation, real-cloud quality/cost, physical safety acceptance, formal heldout/G1/G2 claims, and final full-suite outcome; no corresponding fresh execution evidence was available to this reviewer. R545 runtime overlay is independently planned. Author's guide/reports are in progress and were intentionally not treated as absent implementation. No claim that a passing CPU mock demonstrates real model performance, nor that a manifest is a complete remote reproduction bundle.

## Preserved raw review evidence

The following verbatim scripts/output preserve the original reproductions within this durable report; their original paths and SHA256 values are in plan.json. Scripts create disposable CPU fixture files under /tmp and do not edit source. Temporary fixture paths are not deliverables.

### r544_review_repro.py

```text
import sys, json, tempfile
from pathlib import Path
import pytest
sys.path[:0]=['/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall','/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src']
from tests.test_molmo_grounded_planner import adapter_fixture, request_scene, SKILLS
from tests.test_molmo_grounded_cli import inputs,args,NativeFixture,admitted
from tests.test_molmo_pointing import native_fixture
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_rgbd_observations import observation_payload
import scripts.probe_molmo_grounded_planner as cli
results=[]
with pytest.MonkeyPatch.context() as mp:
 adapter,_,_=adapter_fixture(mp)
 raw='{"skills":[],"skills":'+json.dumps(SKILLS)+'}'
 mp.setattr(adapter.cloud,'_request_visual',lambda *a: {'choices':[{'message':{'content':raw}}]})
 result=PlanningPipeline(planner=adapter).process(request_scene())
 results.append({'case':'duplicate_cloud_skills','raw':raw,'outcome':result.outcome.value,'parse_error':result.attempts[0].draft.parse_error})
with tempfile.TemporaryDirectory(prefix='r544-paid-') as t,pytest.MonkeyPatch.context() as mp:
 p=Path(t); _,_,r,d=inputs(p); model=p/'model'; model.mkdir(); manifest=p/'manifest';manifest.write_text('{}')
 mp.setattr(cli,'MolmoPointProvider',NativeFixture);mp.setattr(cli,'_admit_resources',admitted)
 def selected(*a):return adapter_fixture(mp,fail=True)[0]
 mp.setattr(cli,'_selected_cloud',selected)
 code=cli.main(args(p,r,d)+['--mode','native','--model-directory',str(model),'--asset-manifest',str(manifest),'--allow-paid'])
 report=json.loads((p/'out/report.json').read_text())
 results.append({'case':'paid_cloud_timeout','exit':code,'diagnostic_passed':report['diagnostic_passed'],'pipeline':report['attempts'][0]['pipeline_outcome'],'paid_starts':report['paid_cloud_calls_started'],'real_cloud_status':report['real_cloud_status'],'raw_files':[str(q.relative_to(p/'out')) for q in (p/'out/raw').rglob('*') if q.is_file()], 'evidence_keys':sorted(report['attempts'][0]['evidence'])})
with tempfile.TemporaryDirectory(prefix='r544-load-') as t,pytest.MonkeyPatch.context() as mp:
 p=Path(t); _,_,r,d=inputs(p); model=p/'model';model.mkdir();manifest=p/'manifest';manifest.write_text('{}')
 def failed_load(**kwargs):
  raw=Path(kwargs['raw_directory']);raw.mkdir(parents=True);(raw/'load-started.json').write_text('{"model_loads_started":1}');(raw/'load-failure.json').write_text('{"model_loads_started":1,"error_type":"RuntimeError"}');raise RuntimeError('fixture failed load')
 mp.setattr(cli,'MolmoPointProvider',failed_load);mp.setattr(cli,'_admit_resources',admitted)
 code=cli.main(args(p,r,d)+['--mode','native','--model-directory',str(model),'--asset-manifest',str(manifest)])
 report=json.loads((p/'out/report.json').read_text())
 results.append({'case':'failed_load','exit':code,'loads':report['model_loads_started'],'raw_manifest':(p/'out/raw-manifest.local.json').exists()})
with tempfile.TemporaryDirectory(prefix='r544-decode-') as t,pytest.MonkeyPatch.context() as mp:
 p=Path(t);provider,*_=native_fixture(p,mp)
 def fail_decode(*a,**k):raise RuntimeError('fixture decoder failure')
 mp.setattr(provider._processor,'decode',fail_decode)
 try:provider.point(RGBDObservation.model_validate(observation_payload()),'red block')
 except RuntimeError:pass
 results.append({'case':'decode_failure_after_generation','starts':provider.generation_calls_started,'completed':provider.generation_calls_completed,'output_ids_retained':(p/'raw/request-0001/output-token-ids.json').exists(),'failure_retained':(p/'raw/request-0001/failure.json').exists()})
print('REVIEW_EVIDENCE='+json.dumps(results,ensure_ascii=False,indent=2))

```

### r544_review_repro.stdout

```text
{"status": "COMPLETED", "execution_mode": "NATIVE", "diagnostic_passed": true, "model_loads_started": 1, "generation_calls_started": 2, "paid_cloud_calls_started": 1}
{"status": "FAILED", "error_type": "RuntimeError"}
REVIEW_EVIDENCE=[
  {
    "case": "duplicate_cloud_skills",
    "raw": "{\"skills\":[],\"skills\":[\"HOME\", \"MOVE_ABOVE\", \"APPROACH\", \"GRASP\", \"LIFT\", \"MOVE_TO_REGION\", \"PLACE\", \"RELEASE\", \"RETREAT\", \"HOME\"]}",
    "outcome": "PLANNED",
    "parse_error": null
  },
  {
    "case": "paid_cloud_timeout",
    "exit": 0,
    "diagnostic_passed": true,
    "pipeline": "PLANNER_FAILED",
    "paid_starts": 1,
    "real_cloud_status": "ATTEMPTED",
    "raw_files": [],
    "evidence_keys": [
      "calibrated_object_height_range_m",
      "calibration_version",
      "camera_to_world",
      "captured_at",
      "checksum_sha256",
      "cloud_messages_sha256",
      "cloud_model",
      "cloud_model_image_count",
      "cloud_request_invoked",
      "cloud_request_settings_hash",
      "depth_consumed_by",
      "depth_convention",
      "depth_sha256",
      "episode_id",
      "estimated_fingertip_clearance_m",
      "estimated_object_center",
      "estimated_object_center_semantics",
      "estimated_object_height_m",
      "fingertip_below_tcp_m",
      "frame_id",
      "grasp_calibration_asset_sha256",
      "grasp_geometry_assumption",
      "grasp_profile",
      "ground_truth_used_for_control",
      "grounded_destination",
      "grounded_target",
      "grounding_semantics",
      "hardware_dispatch",
      "height",
      "input_mode",
      "intrinsics",
      "local_support_height_m",
      "minimum_fingertip_clearance_m",
      "model_image_count",
      "native_results",
      "observation_id",
      "opencv_initial_geometry",
      "original_pixel_destination",
      "original_pixel_target",
      "perception_input_mode",
      "perception_model",
      "perception_model_image_count",
      "resolved_top_grasp_tcp",
      "rgb_sha256",
      "scene_id",
      "sim_time_s",
      "source",
      "target_relief_above_support_m",
      "target_visible_surface",
      "task_descriptor_sha256",
      "top_grasp_offset_from_surface_m",
      "top_grasp_offset_status",
      "top_grasp_support_height_m",
      "top_patch_world_z_span_m",
      "width"
    ]
  },
  {
    "case": "failed_load",
    "exit": 2,
    "loads": 1,
    "raw_manifest": false
  },
  {
    "case": "decode_failure_after_generation",
    "starts": 1,
    "completed": 0,
    "output_ids_retained": false,
    "failure_retained": true
  }
]

```

### r544_review_repro.stderr

```text

```

### r544_binding_repro.py

```text
import sys,json
sys.path[:0]=['/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall','/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src']
import pytest
from tests.test_molmo_grounded_planner import adapter_fixture,request_scene,FixturePoints
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
for case in ('observation','instruction','descriptor'):
 with pytest.MonkeyPatch.context() as mp:
  request=request_scene();original=request.observation.checksum_sha256; replacement=request_scene().observation
  adapter,_,bodies=adapter_fixture(mp)
  original_call=adapter.cloud._request_visual
  def change(*args):
   response=original_call(*args)
   if case=='observation':request.observation=replacement
   elif case=='instruction':request.user_instruction='Move the blue cylinder to the yellow region.'
   else:adapter.task=adapter.task.model_copy(update={'target_label':'blue cylinder'})
   return response
  mp.setattr(adapter.cloud,'_request_visual',change)
  result=PlanningPipeline(planner=adapter).process(request)
  print(json.dumps({'case':case,'outcome':result.outcome.value,'request_checksum':request.observation.checksum_sha256,'evidence_checksum':result.attempts[0].draft.observation_evidence['checksum_sha256'],'contract_instruction':result.contract.user_instruction if result.contract else None,'contract_object_class':result.contract.task_target.object_class if result.contract else None}))

```

### r544_binding_repro.stdout

```text
{"case": "observation", "outcome": "PLANNED", "request_checksum": "a3c2159f5477e8c247a638cf0a7760f8ca9e5d2f6db31e0b4e08340e2ab7eac6", "evidence_checksum": "6919d32f4d311710585aca50d07e6d0021e8b6b0d64cc8c996129fcc9888bd2a", "contract_instruction": "Move the red block to the green region.", "contract_object_class": "red block"}
{"case": "instruction", "outcome": "PLANNED", "request_checksum": "f20886aece6cd10e04b290d5b8664ce15f3c5f4400f56a82aaba8fe36fa42d34", "evidence_checksum": "f20886aece6cd10e04b290d5b8664ce15f3c5f4400f56a82aaba8fe36fa42d34", "contract_instruction": "Move the blue cylinder to the yellow region.", "contract_object_class": "red block"}
{"case": "descriptor", "outcome": "PLANNED", "request_checksum": "5027c12802430286c0ec685d3e7ecf52dd2bcb1acad1ad3e7cfe4cc4716c3760", "evidence_checksum": "5027c12802430286c0ec685d3e7ecf52dd2bcb1acad1ad3e7cfe4cc4716c3760", "contract_instruction": "Move the red block to the green region.", "contract_object_class": "red block"}

```

### r544_binding_repro.stderr

```text

```

### r544_review_tests.stdout

```text
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 1.01s

```

### r544_review_tests.stderr

```text

```

### r544_review_ruff.stdout

```text

```

### r544_review_ruff.stderr

```text
ruff failed
  Cause: Failed to create temporary file
  Cause: Read-only file system (os error 30) at path "/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/.ruff_cache/0.14.14/.tmp19lENK"

```

### r544_review_ruff_nocache.stdout

```text
E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:24:1
   |
22 |     sys.path.insert(0, str(ROOT / "src"))
23 |
24 | from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
25 | from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
26 | from cloud_edge_robot_arm.vision.grounded_planner import (
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:25:1
   |
24 | from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
25 | from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
26 | from cloud_edge_robot_arm.vision.grounded_planner import (
27 |     GroundingTaskDescriptor,
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:26:1
   |
24 |   from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
25 |   from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
26 | / from cloud_edge_robot_arm.vision.grounded_planner import (
27 | |     GroundingTaskDescriptor,
28 | |     MolmoGroundedPlannerAdapter,
29 | |     build_molmo_grounded_planner,
30 | | )
   | |_^
31 |   from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
32 |   from cloud_edge_robot_arm.vision.molmo_pointing import (
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:31:1
   |
29 |     build_molmo_grounded_planner,
30 | )
31 | from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
32 | from cloud_edge_robot_arm.vision.molmo_pointing import (
33 |     BoundPointResult,
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:32:1
   |
30 |   )
31 |   from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
32 | / from cloud_edge_robot_arm.vision.molmo_pointing import (
33 | |     BoundPointResult,
34 | |     MolmoPointProvider,
35 | |     parse_native_point,
36 | | )
   | |_^
37 |   from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
38 |   from cloud_edge_robot_arm.vision.role_models import configuration_hash
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:37:1
   |
35 |     parse_native_point,
36 | )
37 | from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
38 | from cloud_edge_robot_arm.vision.role_models import configuration_hash
   |

E402 Module level import not at top of file
  --> scripts/probe_molmo_grounded_planner.py:38:1
   |
36 | )
37 | from cloud_edge_robot_arm.vision.planner import RGBDModelUnavailable, RGBDPlannerAdapter
38 | from cloud_edge_robot_arm.vision.role_models import configuration_hash
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   |

Found 7 errors.

```

### r544_review_ruff_nocache.stderr

```text

```
