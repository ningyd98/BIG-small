"""Re-read recorded high motion and the real terminal collision, without advancing MuJoCo."""

from dataclasses import replace

from recovery_boundary import Refused, check_stationary
from recovery_native import FROZEN, GEN, OLD, PLAN, RAW, ROUND, WORK, measured_state, native

# isort: split
# recovery_native pins the frozen worker before these imports.
from scripts.graduation import proposal_camera
from scripts.graduation.perception_io import pinned, read, sha, write


def main():
    source = OLD / "batches/train-radial30-contact-d02-02/d02"
    plan = pinned(ROUND / "plan.json", PLAN)
    info = pinned(
        source / "allocation.json",
        plan["inputs_sha256"][str((source / "allocation.json").relative_to(WORK))],
    )
    seal = read(source / "instance/acquisition-seal.json")
    truth = pinned(source / "instance/offline-truth.json", seal["truth_sha256"])
    original = read(source / "instance/run.json")
    backend = native.MuJoCoPhysicsBackend()
    cfg = native.SimulatorConfig(
        model_path=str(FROZEN / info["geometry"]["asset_path"]),
        seed=1,
        render_rgb=False,
        render_depth=False,
    )
    backend.initialize(cfg)
    backend.reset(
        native.PhysicalScenarioConfig(
            scenario_id="historical-hard-readback",
            seed=1,
            object_pose=native.Pose(x=0.45, y=0, z=0.035),
            object_mass_kg=info["case"]["physical_object_mass_kg"],
        )
    )
    robot = native.MuJoCoSkillRobot(backend)
    restored = []
    samples = []
    try:
        for i in (136, 144, 152, 1227, 1228):
            row = truth["samples"][i]
            residual = proposal_camera.restore(backend._model, backend._data, row)
            assert row["physics_step"] == i
            # get_contacts() normally receives this cache at the end of mj_step. Here only
            # restore + mj_forward are allowed; rebuild it using that same native contact extractor.
            backend._last_contacts = backend._read_contacts()
            contacts = native.plain(backend.get_contacts())
            failure = None
            try:
                native.check_component_hard_state(backend, robot)
            except native.ComponentStopped as error:
                failure = str(error)
            state = replace(measured_state(backend), step=i)
            restored.append(
                dict(
                    source_step=i,
                    velocities=state.joint_velocities,
                    pose_residual=residual,
                    max_speed_rad_s=max(map(abs, state.joint_velocities)),
                    illegal_geometries=[[c["geom1"], c["geom2"]] for c in contacts if c["illegal"]],
                    hard_state_refusal=failure,
                )
            )
            if i <= 152:
                samples.append(state)
        try:
            check_stationary(samples)
        except Refused as exc:
            moving = str(exc)
        else:
            raise AssertionError("actual moving high trajectory accepted as stationary")
        assert [s["hard_state_refusal"] for s in restored[-2:]] == [None, "ROBOT_HARD_SAFETY_STOP"]
        assert ["left_finger_geom", "g1_dual_id7_crossbar"] in restored[-1][
            "illegal_geometries"
        ] or ["g1_dual_id7_crossbar", "left_finger_geom"] in restored[-1]["illegal_geometries"]
        assert backend.total_physics_steps == 0 and not backend.command_records
        obj = dict(
            schema="g1.cv.stationary-recovery.historical-hard-state.v1",
            plan_sha256=PLAN,
            original_generation=GEN,
            scope="independent reconstruction from recorded real trajectory",
            rows=restored,
            original_run_stop=original["stop"],
            moving_refusal=moving,
            offline_steps_advanced=0,
            offline_controller_commands=0,
            raw_inputs_sha256={
                str(p.relative_to(WORK)): sha(p)
                for p in (
                    source / "allocation.json",
                    source / "instance/acquisition-seal.json",
                    source / "instance/offline-truth.json",
                    source / "instance/run.json",
                )
            },
        )
        write(RAW / "historical-hard-state.json", obj)
    finally:
        backend.shutdown()


if __name__ == "__main__":
    main()
