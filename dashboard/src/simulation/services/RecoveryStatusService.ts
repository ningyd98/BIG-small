type RecoveryStatus = {
  recovered_jobs: string[];
  interrupted_jobs: string[];
  incomplete_artifacts: string[];
  rerun_started: boolean;
};

export class RecoveryStatusService {
  private readonly status: RecoveryStatus;

  constructor(status: RecoveryStatus) {
    this.status = { ...status };
  }

  hasBlockers(): boolean {
    return this.status.incomplete_artifacts.length > 0;
  }

  summary(): string {
    return `${this.status.recovered_jobs.length} recovered, ${this.status.interrupted_jobs.length} interrupted`;
  }

  snapshot(): RecoveryStatus {
    return { ...this.status };
  }
}
