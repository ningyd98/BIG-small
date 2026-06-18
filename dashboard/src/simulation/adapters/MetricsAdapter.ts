// 指标适配器，保证单位、来源和聚合方式在前端一致。
import type { SimulationMetric } from "../domain/RunMetric";

export function numericMetricValues(
  metrics: SimulationMetric[],
  name: string,
): number[] {
  return metrics
    .filter(
      (metric) => metric.name === name && typeof metric.value === "number",
    )
    .map((metric) => Number(metric.value));
}
