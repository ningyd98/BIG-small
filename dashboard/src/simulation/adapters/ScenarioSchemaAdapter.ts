import type { ScenarioDefinition } from "../domain/ScenarioDefinition";

export function scenarioLabel(scenario: ScenarioDefinition): string {
  return `${scenario.scenario_id} - ${scenario.description}`;
}
