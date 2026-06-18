type Attempt = {
  attempt: number;
  worker_id: string;
  started_at: string;
  ended_at?: string | null;
  result: string;
  error: string;
  artifact_paths: Record<string, string>;
};

export class AttemptHistoryService {
  private readonly attempts: Attempt[];

  constructor(attempts: Attempt[]) {
    this.attempts = attempts.map((attempt) => ({ ...attempt }));
  }

  latest(): Attempt | undefined {
    return [...this.attempts].sort(
      (left, right) => right.attempt - left.attempt,
    )[0];
  }

  failedAttempts(): Attempt[] {
    return this.attempts.filter((attempt) =>
      ["FAILED", "TIMED_OUT", "CANCELLED"].includes(attempt.result),
    );
  }

  all(): Attempt[] {
    return this.attempts.map((attempt) => ({ ...attempt }));
  }
}
