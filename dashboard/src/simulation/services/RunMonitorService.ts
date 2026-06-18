type StreamEvent = {
  sequence: number;
  event_type: string;
  run_id?: string;
  experiment_id?: string;
  [key: string]: unknown;
};

export class RunMonitorService {
  private events = new Map<string, StreamEvent[]>();
  private seenSequences = new Set<number>();
  private lastSequence = 0;
  private sequenceGap = false;
  private lastSeenAt = Date.now();
  private staleAfterMs: number;

  constructor(options: { staleAfterMs: number }) {
    this.staleAfterMs = options.staleAfterMs;
  }

  ingest(event: StreamEvent): void {
    if (this.seenSequences.has(event.sequence)) return;
    if (event.sequence > this.lastSequence + 1 && this.lastSequence !== 0) {
      this.sequenceGap = true;
    }
    this.seenSequences.add(event.sequence);
    this.lastSequence = Math.max(this.lastSequence, event.sequence);
    this.lastSeenAt = Date.now();
    const runId = event.run_id || event.experiment_id || "global";
    this.events.set(runId, [...(this.events.get(runId) ?? []), event]);
  }

  eventsFor(runId: string): StreamEvent[] {
    return [...(this.events.get(runId) ?? [])];
  }

  sequenceGapDetected(): boolean {
    return this.sequenceGap;
  }

  reconnectMessage(): { last_sequence: number } {
    return { last_sequence: this.lastSequence };
  }

  isStale(now = Date.now()): boolean {
    return now - this.lastSeenAt > this.staleAfterMs;
  }
}
