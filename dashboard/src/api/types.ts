import type { components } from "./generated/schema";

export type DashboardSummary = components["schemas"]["DashboardSummary"];
export type DashboardCapabilities =
  components["schemas"]["cloud_edge_robot_arm__dashboard__models__CapabilitiesResponse"];
export type DashboardEvidenceRecord =
  components["schemas"]["EvidenceIndexRecord"];
export type DashboardEvidenceList =
  components["schemas"]["EvidenceListResponse"];
export type DashboardEvidenceDetail =
  components["schemas"]["EvidenceDetailResponse"];
export type DashboardExperimentCreateRequest =
  components["schemas"]["ExperimentCreateRequest"];
export type DashboardExperimentJob =
  components["schemas"]["ExperimentJobRecord"];
export type DashboardExperimentList =
  components["schemas"]["ExperimentListResponse"];
export type DashboardAcceptanceSnapshot =
  components["schemas"]["AcceptanceLevelSnapshot"];
export type DashboardComparison = components["schemas"]["ComparisonResponse"];
export type DashboardAuditEvents = components["schemas"]["AuditEventResponse"];
export type DashboardRuntime = components["schemas"]["RuntimeSnapshot"];
export type DashboardSafety = components["schemas"]["SafetyGateSnapshot"];
export type DashboardSafetyReviewNoteRequest =
  components["schemas"]["SafetyReviewNoteRequest"];
export type DashboardSafetyReviewNoteResponse =
  components["schemas"]["SafetyReviewNoteResponse"];
export type DashboardUserRole =
  | "VIEWER"
  | "EXPERIMENT_OPERATOR"
  | "SAFETY_REVIEWER";
