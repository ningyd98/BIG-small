import { Navigate, Route, Routes } from "react-router-dom";
import { lazy, Suspense } from "react";

import { NotFoundPage } from "../pages/NotFoundPage";
import { OverviewPage } from "../pages/OverviewPage";

const AuditLogPage = lazy(() =>
  import("../pages/AuditLogPage").then((module) => ({
    default: module.AuditLogPage,
  })),
);
const ComparisonPage = lazy(() =>
  import("../pages/ComparisonPage").then((module) => ({
    default: module.ComparisonPage,
  })),
);
const EvidenceExplorerPage = lazy(() =>
  import("../pages/EvidenceExplorerPage").then((module) => ({
    default: module.EvidenceExplorerPage,
  })),
);
const SafetyAcceptancePage = lazy(() =>
  import("../pages/SafetyAcceptancePage").then((module) => ({
    default: module.SafetyAcceptancePage,
  })),
);
const SimulationLabPage = lazy(() =>
  import("../pages/SimulationLabPage").then((module) => ({
    default: module.SimulationLabPage,
  })),
);
const TaskExecutionPage = lazy(() =>
  import("../pages/TaskExecutionPage").then((module) => ({
    default: module.TaskExecutionPage,
  })),
);

export function DashboardRoutes() {
  return (
    <Suspense fallback={null}>
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
    </Suspense>
  );
}
