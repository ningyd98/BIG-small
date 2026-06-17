import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dashboardApi } from "./client";
import type {
  DashboardExperimentCreateRequest,
  DashboardSafetyReviewNoteRequest,
  DashboardUserRole,
} from "./types";

const DEFAULT_ROLE: DashboardUserRole = "VIEWER";

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => dashboardApi.summary(DEFAULT_ROLE),
    refetchInterval: 5_000,
  });
}

export function useDashboardCapabilities(
  role: DashboardUserRole = DEFAULT_ROLE,
) {
  return useQuery({
    queryKey: ["dashboard", "capabilities", role],
    queryFn: () => dashboardApi.capabilities(role),
    staleTime: 30_000,
  });
}

export function useDashboardExperiments() {
  return useQuery({
    queryKey: ["dashboard", "experiments"],
    queryFn: () => dashboardApi.experiments(DEFAULT_ROLE),
    refetchInterval: 1_000,
  });
}

export function useStartExperimentMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DashboardExperimentCreateRequest) =>
      dashboardApi.startExperiment(body, "EXPERIMENT_OPERATOR"),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "experiments"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "summary"],
      });
    },
  });
}

export function useCancelExperimentMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (experimentId: string) =>
      dashboardApi.cancelExperiment(experimentId, "EXPERIMENT_OPERATOR"),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "experiments"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "summary"],
      });
    },
  });
}

export function useDashboardAcceptance() {
  return useQuery({
    queryKey: ["dashboard", "acceptance"],
    queryFn: () => dashboardApi.acceptance(DEFAULT_ROLE),
  });
}

export function useRecordSafetyReviewNoteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DashboardSafetyReviewNoteRequest) =>
      dashboardApi.recordSafetyReviewNote(body, "SAFETY_REVIEWER"),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["dashboard", "audit-events"],
      });
    },
  });
}

export function useDashboardComparison() {
  return useQuery({
    queryKey: ["dashboard", "comparisons"],
    queryFn: () => dashboardApi.comparisons(DEFAULT_ROLE),
  });
}

export function useDashboardAuditEvents() {
  return useQuery({
    queryKey: ["dashboard", "audit-events"],
    queryFn: () => dashboardApi.auditEvents(DEFAULT_ROLE),
    refetchInterval: 5_000,
  });
}

export function useDashboardRuntime() {
  return useQuery({
    queryKey: ["dashboard", "runtime"],
    queryFn: () => dashboardApi.runtime(DEFAULT_ROLE),
    refetchInterval: 5_000,
  });
}
