import importlib.util, json, sys, tempfile
from pathlib import Path
root=Path.cwd()
p=root/"artifacts/research/process/20261004-ced-development/astra-repair-execution/R01/marker-v4-preparation"
spec=importlib.util.spec_from_file_location("independent_v4_exact_range_red",p/"run_sparse_once.py")
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
header=json.loads((p/"pilot-protocol/header.json").read_text())
base=m.configured_runner(header)
selected=tuple(header["selected_steps"])
expected=header["expected_physics_steps"]
assert expected==4806 and len(selected)==201 and selected[-1]==4806
class Observation:
    episode_id="independent-pure-cpu"
    def __init__(self,n):
        self.sim_time_s=n/240
        self.observation_id=f"independent-cpu-{n}"
        self.checksum_sha256="cpu-observation-contract-fixture"
    def model_dump_json(self):
        return json.dumps({"observation_id":self.observation_id,"sim_time_s":self.sim_time_s})
def run(final_step):
    current=[0]
    def capture():return Observation(current[0]),["equal-registered-state","equal-registered-state"]
    directory=Path(tempfile.mkdtemp(prefix="bigsmall-v4-range-red-"))/"series"
    recorder=base.StepRGBDRecorder(directory,capture,episode_id=Observation.episode_id,max_sample_gap_s=header["original_max_sample_gap_s"])
    for n in range(final_step+1):
        current[0]=n
        recorder.observe_step(episode_id=Observation.episode_id,physics_step=n,sim_time_s=n/240)
        if n in selected:recorder.record_step(episode_id=Observation.episode_id,physics_step=n,sim_time_s=n/240)
    summary=recorder.finish(final_step=final_step,final_sim_time_s=final_step/240)
    rows=[json.loads(line) for line in (directory/"index.jsonl").read_text().splitlines()]
    callbacks=[row for row in rows if row["event"]=="PHYSICAL_CALLBACK"]
    assert [row["physics_step"] for row in callbacks]==list(range(final_step+1))
    assert summary["saved_steps"]==list(selected) and len(summary["allocated_steps"])==201
    assert summary["planned_selected_steps"]==list(selected) and not summary["missing_selected_steps"]
    assert len(list((directory/"frames").glob("*.json.gz")))==201
    return {"final_step":final_step,"status":summary["status"],"physical_callbacks":summary["physical_callbacks"],"saved_selected_count":len(summary["saved_steps"]),"last_retained_callback":callbacks[-1],"missing_selected_steps":summary["missing_selected_steps"],"scope":summary["scope"],"directory":str(directory)}
healthy=run(expected)
deviation=run(expected+1)
print(json.dumps({"qualified_counterexample":"R01-V4-RANGE-01","frozen_expected_physics_steps":expected,"frozen_expected_physics_steps_is_admission_gate":header["expected_physics_steps_is_admission_gate"],"healthy":healthy,"deviation":deviation,"actual_model_renderer_physics_decoder_provider_calls":0},indent=2),flush=True)
assert healthy["status"]=="COMPLETE"
assert deviation["status"]!="COMPLETE", "R01-V4-RANGE-01: actual final_step 4807 was labelled COMPLETE for fixed original 4806 diagnostic range"
