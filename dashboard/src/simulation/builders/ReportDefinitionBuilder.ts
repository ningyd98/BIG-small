// 报告定义构建器，声明导出格式、指标和脱敏要求。
export type ReportDefinition = {
  title: string;
  includeMetrics: string[];
  includeEvents: boolean;
  includeArtifacts: boolean;
};

export class ReportDefinitionBuilder {
  static paperTable(metrics: string[]): ReportDefinition {
    return {
      title: "Phase 11 Simulation Workbench Report",
      includeMetrics: metrics,
      includeEvents: true,
      includeArtifacts: true,
    };
  }
}
