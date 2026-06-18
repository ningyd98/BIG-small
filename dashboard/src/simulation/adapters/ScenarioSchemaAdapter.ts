// 场景 schema 适配器，把后端 S01-S15 定义转换为浏览器可展示结构。
import type { ScenarioDefinition } from "../domain/ScenarioDefinition";

export function scenarioLabel(scenario: ScenarioDefinition): string {
  return `${scenario.scenario_id} - ${scenario.description}`;
}
