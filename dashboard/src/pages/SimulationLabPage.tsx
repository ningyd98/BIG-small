// 兼容旧仿真实验路由，实际委托到新的 Simulation Workbench。
import { SimulationWorkbenchPage } from "../simulation/pages/SimulationWorkbenchPage";

export function SimulationLabPage() {
  return <SimulationWorkbenchPage />;
}
