import { useQuery } from "@tanstack/react-query";

import { dashboardApi } from "./client";

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: dashboardApi.summary,
    refetchInterval: 5_000,
  });
}

export function useDashboardCapabilities() {
  return useQuery({
    queryKey: ["dashboard", "capabilities"],
    queryFn: dashboardApi.capabilities,
    staleTime: 30_000,
  });
}
