type QueueStatus = {
  queued: number;
  running: number;
  blocked: number;
  max_queued_jobs: number;
  max_batch_runs: number;
};

export class QueueMonitorService {
  private readonly status: QueueStatus;

  constructor(status: QueueStatus) {
    this.status = status;
  }

  isNearCapacity(): boolean {
    return this.status.max_queued_jobs > 0
      ? this.status.queued / this.status.max_queued_jobs >= 0.8
      : false;
  }

  summary(): string {
    return `${this.status.queued} queued, ${this.status.running} running, ${this.status.blocked} blocked`;
  }

  snapshot(): QueueStatus {
    return { ...this.status };
  }
}
