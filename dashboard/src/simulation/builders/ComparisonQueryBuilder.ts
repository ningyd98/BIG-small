// 对比查询构建器，确保 paired backend 和模式对比条件一致。
import type { components } from "../../api/generated/schema";

export class ComparisonQueryBuilder {
  static modeComparison(
    runIds: string[],
  ): components["schemas"]["ComparisonRequest"] {
    return {
      comparison_type: "MODE_COMPARISON",
      run_ids: runIds,
      paired_key: {},
    };
  }

  static pairedBackend(
    runIds: string[],
    pairedKey: Record<string, string | number | boolean>,
  ): components["schemas"]["ComparisonRequest"] {
    return {
      comparison_type: "CROSS_BACKEND_PAIRED",
      run_ids: runIds,
      paired_key: pairedKey,
    };
  }
}
