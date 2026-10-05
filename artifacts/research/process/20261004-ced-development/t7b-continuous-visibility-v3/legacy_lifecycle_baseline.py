"""Historical journal lifecycle semantics adapter, SOFTWARE_ONLY RED evidence."""


class AcquisitionCoordinator:
    def __init__(self, backend, journal, series, tracker, adapter):
        self.backend, self.journal, self.series = backend, journal, series
        self.tracker, self.adapter = tracker, adapter
        self.allocated = self.completed = self.failed = 0
        self.failure_journal_errors = []

    def record(self, snapshot):
        self.allocated += 1
        self.journal.emit("ACQUISITION_BEGIN")
        try:
            row = self.series.record_step(episode_id=snapshot.episode_id,
                                          physics_step=snapshot.physics_step,
                                          sim_time_s=snapshot.sim_time_s)
            self.completed += 1
            self.journal.emit("ACQUISITION_END")
            return row
        except BaseException as error:
            self.failed += 1
            self.journal.emit("ACQUISITION_FAILED", error=str(error))
            raise
