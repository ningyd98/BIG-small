export type HardwareClaim =
  | "NONE"
  | "SIMULATION_ONLY"
  | "PLANNING_ONLY"
  | "HARDWARE_READ_ONLY"
  | "HARDWARE_MOTION";

export type DashboardSummary = {
  current_project_status: string;
  real_robot_validation: string;
  highest_acceptance_level: string;
  hardware_claim: HardwareClaim;
  worktree_clean: boolean;
  software_commit: string;
  source_tree_hash: string;
  runtime_profile?: string;
  services: Array<{ name: string; status: string; detail?: string }>;
  blockers: string[];
  latest_evidence: Array<{
    evidence_id: string;
    phase: string;
    status: string;
    hardware_claim: HardwareClaim;
    relative_path: string;
  }>;
  active_experiments: Array<{ experiment_id: string; status: string }>;
  safety_summary: {
    hardware_motion_authorized: boolean;
    reason_codes: string[];
  };
};

export type DashboardCapabilities = {
  hardware_write_operations: string[];
  allowed_write_operations: string[];
  supported_pages?: string[];
};
