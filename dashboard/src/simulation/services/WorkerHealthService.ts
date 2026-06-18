type WorkerStatus = {
  worker_id: string;
  backend: string;
  status: string;
  active_job_id: string;
  lease_id: string;
  heartbeat_at?: string | null;
};

export class WorkerHealthService {
  private readonly workers: WorkerStatus[];

  constructor(workers: WorkerStatus[]) {
    this.workers = workers.map((worker) => ({ ...worker }));
  }

  busyCount(): number {
    return this.workers.filter((worker) => worker.status === "BUSY").length;
  }

  backends(): string[] {
    return [...new Set(this.workers.map((worker) => worker.backend))];
  }

  all(): WorkerStatus[] {
    return this.workers.map((worker) => ({ ...worker }));
  }
}
