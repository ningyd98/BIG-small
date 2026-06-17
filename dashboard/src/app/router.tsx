import { Navigate, Route, Routes } from "react-router-dom";

import { AuditLogPage } from "../pages/AuditLogPage";
import { ComparisonPage } from "../pages/ComparisonPage";
import { EvidenceExplorerPage } from "../pages/EvidenceExplorerPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";
import { SafetyAcceptancePage } from "../pages/SafetyAcceptancePage";
import { SimulationLabPage } from "../pages/SimulationLabPage";
import { TaskExecutionPage } from "../pages/TaskExecutionPage";

export function DashboardRoutes() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/simulation" element={<SimulationLabPage />} />
      <Route path="/task-execution" element={<TaskExecutionPage />} />
      <Route path="/safety-acceptance" element={<SafetyAcceptancePage />} />
      <Route path="/evidence" element={<EvidenceExplorerPage />} />
      <Route path="/comparison" element={<ComparisonPage />} />
      <Route path="/audit" element={<AuditLogPage />} />
      <Route path="/overview" element={<Navigate to="/" replace />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
