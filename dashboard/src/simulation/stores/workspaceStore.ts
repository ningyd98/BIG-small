// 工作台 store，保存 UI 过滤器、布局和最近使用选项。
export type SimulationWorkspace = {
  activeBackend: string;
  activeScenario: string;
};

let workspace: SimulationWorkspace = {
  activeBackend: "MOCK",
  activeScenario: "S01_NORMAL_STATIC",
};

export function setWorkspace(next: SimulationWorkspace): void {
  workspace = { ...next };
}

export function getWorkspace(): SimulationWorkspace {
  return { ...workspace };
}
