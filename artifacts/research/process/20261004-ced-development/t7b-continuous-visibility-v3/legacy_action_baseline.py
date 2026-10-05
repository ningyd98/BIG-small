"""SOFTWARE_ONLY original action publication ordering counterexample."""
class ActionTracker:
    def __init__(self, backend, journal):
        self.backend, self.journal = backend, journal
        self.current = None
        self.begins = self.ends = 0
        self.returned = []

    def invoke(self, action_type, original, *args, **kwargs):
        self.journal.ensure(self.backend)
        if self.current is not None:
            raise RuntimeError("unexpected nested original action")
        ordinal = self.begins + 1
        start_step = self.backend.total_physics_steps
        command_start = len(self.backend.command_records) + 1
        self.journal.emit(
            "ACTION_BEGIN",
            action_ordinal=ordinal,
            action_type=action_type,
            episode_id=self.backend._episode_id,
            start_step=start_step,
            sim_time_s=self.backend.get_sim_time(),
            command_seq_start=command_start,
            arguments=args,
            keyword_arguments=kwargs,
        )
        self.begins += 1
        self.current = ordinal
        result = error = None
        try:
            result = original(*args, **kwargs)
            self.returned.append(
                {
                    "action_ordinal": ordinal,
                    "start_step": start_step,
                    "end_step": self.backend.total_physics_steps,
                    "command_seq_start": command_start,
                    "command_seq_end": len(self.backend.command_records) + 1,
                }
            )
            return result
        except BaseException as exception:
            error = exception
            raise
        finally:
            self.current = None
            self.ends += 1
            try:
                self.journal.emit(
                    "ACTION_END",
                    action_ordinal=ordinal,
                    action_type=action_type,
                    episode_id=self.backend._episode_id,
                    start_step=start_step,
                    end_step=self.backend.total_physics_steps,
                    sim_time_s=self.backend.get_sim_time(),
                    command_seq_start=command_start,
                    command_seq_end=len(self.backend.command_records) + 1,
                    result=result,
                    error_type=type(error).__name__ if error else None,
                    error=str(error) if error else None,
                )
                if error is None:
                    self.journal.ensure(self.backend)
            except BaseException:
                if error is None:
                    raise

