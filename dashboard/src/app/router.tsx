// Dashboard 路由表，保留旧页面路径并接入仿真工作台页面。
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
const ScenarioLibraryPage = lazy(() =>
  import("../simulation/pages/ScenarioLibraryPage").then((module) => ({
    default: module.ScenarioLibraryPage,
  })),
);
const BatchExperimentPage = lazy(() =>
  import("../simulation/pages/BatchExperimentPage").then((module) => ({
    default: module.BatchExperimentPage,
  })),
);
const LiveRunPage = lazy(() =>
  import("../simulation/pages/LiveRunPage").then((module) => ({
    default: module.LiveRunPage,
  })),
);
const ResultAnalysisPage = lazy(() =>
  import("../simulation/pages/ResultAnalysisPage").then((module) => ({
    default: module.ResultAnalysisPage,
  })),
);
const ModeComparisonPage = lazy(() =>
  import("../simulation/pages/ModeComparisonPage").then((module) => ({
    default: module.ModeComparisonPage,
  })),
);
const CrossBackendComparisonPage = lazy(() =>
  import("../simulation/pages/CrossBackendComparisonPage").then((module) => ({
    default: module.CrossBackendComparisonPage,
  })),
);
const ModelControlCenterPage = lazy(() =>
  import("../modelControl/pages/ModelControlCenterPage").then((module) => ({
    default: module.ModelControlCenterPage,
  })),
);
const LocalModelsPage = lazy(() =>
  import("../modelControl/pages/LocalModelsPage").then((module) => ({
    default: module.LocalModelsPage,
  })),
);
const ProviderProfilesPage = lazy(() =>
  import("../modelControl/pages/ProviderProfilesPage").then((module) => ({
    default: module.ProviderProfilesPage,
  })),
);
const ModelDownloadCenterPage = lazy(() =>
  import("../modelControl/pages/ModelDownloadCenterPage").then((module) => ({
    default: module.ModelDownloadCenterPage,
  })),
);
const PlannerTestConsolePage = lazy(() =>
  import("../modelControl/pages/PlannerTestConsolePage").then((module) => ({
    default: module.PlannerTestConsolePage,
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
        <Route path="/simulation/scenarios" element={<ScenarioLibraryPage />} />
        <Route path="/simulation/batch" element={<BatchExperimentPage />} />
        <Route path="/simulation/live" element={<LiveRunPage />} />
        <Route path="/simulation/analysis" element={<ResultAnalysisPage />} />
        <Route path="/simulation/modes" element={<ModeComparisonPage />} />
        <Route
          path="/simulation/backends"
          element={<CrossBackendComparisonPage />}
        />
        <Route path="/models" element={<ModelControlCenterPage />} />
        <Route path="/models/providers" element={<ProviderProfilesPage />} />
        <Route path="/models/local" element={<LocalModelsPage />} />
        <Route path="/models/downloads" element={<ModelDownloadCenterPage />} />
        <Route path="/models/test" element={<PlannerTestConsolePage />} />
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
