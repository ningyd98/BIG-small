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
