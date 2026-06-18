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
