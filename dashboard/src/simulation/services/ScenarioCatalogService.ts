// 场景目录服务：从后端 scenario registry 数据构建筛选结果，避免 React 页面硬编码场景。
import type {
  ScenarioDefinition,
  ScenarioFilter,
} from "../domain/ScenarioDefinition";

// ScenarioCatalogService 只消费后端 scenario_registry 投影，避免 React 页面硬编码 S01-S15。
export class ScenarioCatalogService {
  constructor(private readonly scenarios: ScenarioDefinition[]) {}

  all(): ScenarioDefinition[] {
    return [...this.scenarios];
  }

  detail(scenarioId: string): ScenarioDefinition | undefined {
    return this.scenarios.find(
      (scenario) => scenario.scenario_id === scenarioId,
    );
  }

  search(query: string): ScenarioDefinition[] {
    const normalized = query.toLowerCase();
    return this.scenarios.filter((scenario) => {
      return (
        scenario.scenario_id.toLowerCase().includes(normalized) ||
        scenario.description.toLowerCase().includes(normalized) ||
        scenario.fault_types.some((fault) =>
          fault.toLowerCase().includes(normalized),
        )
      );
    });
  }

  filter(filters: ScenarioFilter): ScenarioDefinition[] {
    return this.scenarios.filter((scenario) => {
      if (filters.category && scenario.category !== filters.category)
        return false;
      if (
        filters.faultType &&
        !scenario.fault_types.includes(filters.faultType)
      )
        return false;
      if (filters.backend) {
        const readiness = scenario.backend_support[filters.backend];
        if (!readiness || readiness === "BLOCKED_BY_ENV") return false;
      }
      if (filters.query && !this.search(filters.query).includes(scenario))
        return false;
      return true;
    });
  }
}
