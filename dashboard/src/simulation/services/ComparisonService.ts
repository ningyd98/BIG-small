import type {
  ComparisonStats,
  PairedBackendRun,
} from "../domain/ComparisonDataset";
import type { SimulationMetric } from "../domain/RunMetric";

export class ComparisonService {
  constructor(private readonly metrics: SimulationMetric[]) {}

  compareModes(
    leftMode: string,
    rightMode: string,
    metricName: string,
  ): ComparisonStats {
    const left = this.valueFor(leftMode, metricName);
    const right = this.valueFor(rightMode, metricName);
    const values = [left, right].filter(Number.isFinite);
    const mean = values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : 0;
    return {
      mean,
      median:
        values.length === 2 ? (values[0] + values[1]) / 2 : (values[0] ?? 0),
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 0,
      standard_deviation:
        values.length === 2
          ? Math.abs(values[1] - values[0]) / Math.sqrt(2)
          : 0,
      success_rate: this.successRate(),
      failure_rate: 1 - this.successRate(),
      percentile: { p95: values.length ? Math.max(...values) : 0 },
      paired_delta: right - left,
      relative_delta: left === 0 ? 0 : (right - left) / left,
    };
  }

  pairedBackendAligned(runs: PairedBackendRun[]): boolean {
    if (runs.length < 2) return false;
    const [first] = runs;
    return runs.every((run) => {
      return (
        run.paired_key === first.paired_key &&
        run.scenario === first.scenario &&
        run.seed === first.seed
      );
    });
  }

  private valueFor(mode: string, name: string): number {
    const metric = this.metrics.find((item) => {
      return item.control_mode === mode && item.name === name;
    });
    return typeof metric?.value === "number" ? metric.value : 0;
  }

  private successRate(): number {
    const success = this.metrics.filter(
      (metric) => metric.name === "task_success",
    );
    if (success.length === 0) return 0;
    return (
      success.filter((metric) => Boolean(metric.value)).length / success.length
    );
  }
}
