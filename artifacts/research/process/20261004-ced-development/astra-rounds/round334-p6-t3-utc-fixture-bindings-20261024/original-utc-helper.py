def _b_t3_utc(scoped, at):
    from datetime import datetime

    class DateTimeMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class ShiftedDateTime(datetime, metaclass=DateTimeMeta):
        @classmethod
        def now(cls, tz=None):
            return at.replace(tzinfo=None) if tz is None else at.astimezone(tz)

    names = ("vision.worker_runtime", "vision.worker_owner", "vision.operational_windows",
             "vision.owner_registration", "vision.execution", "vision.supervision",
             "simulation_runtime.worker", "repositories.event_autonomy.visual_bootstrap",
             "repositories.event_autonomy.visual_supervision", "repositories.event_autonomy.visual_owner",
             "repositories.event_autonomy.visual_verification", "repositories.event_autonomy.memory",
             "repositories.event_autonomy.sqlite", "edge.recovery.verification_router",
             "edge.recovery.lifecycle", "edge.evidence.conditions", "cloud.planning.pipeline")
    for name in names:
        module = importlib.import_module("cloud_edge_robot_arm." + name)
        assert hasattr(module, "datetime"), name
        scoped.setattr(module, "datetime", ShiftedDateTime)

