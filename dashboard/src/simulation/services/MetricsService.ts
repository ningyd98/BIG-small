import type { MetricSummary, SimulationMetric } from "../domain/RunMetric";

export class MetricsService {
  constructor(private readonly metrics: SimulationMetric[]) {}

  summary(): MetricSummary {
    const units: Record<string, string> = {};
    const sampleCounts: Record<string, number> = {};
    for (const metric of this.metrics) {
      units[metric.name] = metric.unit;
      sampleCounts[metric.name] =
        (sampleCounts[metric.name] ?? 0) + metric.sample_count;
    }
    return {
      units,
      sampleCounts,
      blockedByEnv: this.metrics.some(
        (metric) => metric.value === "BLOCKED_BY_ENV",
      ),
    };
  }

  byName(name: string): SimulationMetric[] {
    return this.metrics.filter((metric) => metric.name === name);
  }
}
