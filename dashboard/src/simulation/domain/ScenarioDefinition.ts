// 场景定义类型，映射后端 scenario_registry 的权威场景。
import type { components } from "../../api/generated/schema";

export type ScenarioDefinition =
  components["schemas"]["ScenarioDefinitionView"];
export type ScenarioCategory = components["schemas"]["ScenarioCategory"];

export type ScenarioFilter = {
  query?: string;
  category?: ScenarioCategory;
  faultType?: string;
  backend?: string;
};
