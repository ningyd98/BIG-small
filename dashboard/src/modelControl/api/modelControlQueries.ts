// React Query hooks for Model Control Center.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { modelControlApi } from "./modelControlApi";

export const modelControlKeys = {
  capabilities: ["model-control", "capabilities"] as const,
  profiles: ["model-control", "profiles"] as const,
  runtime: ["model-control", "runtime"] as const,
  ollamaStatus: ["model-control", "ollama-status"] as const,
  ollamaModels: ["model-control", "ollama-models"] as const,
  catalog: ["model-control", "catalog"] as const,
  downloads: ["model-control", "downloads"] as const,
};

export function useModelCapabilities() {
  return useQuery({
    queryKey: modelControlKeys.capabilities,
    queryFn: modelControlApi.capabilities,
  });
}

export function useModelProfiles() {
  return useQuery({
    queryKey: modelControlKeys.profiles,
    queryFn: modelControlApi.profiles,
  });
}

export function usePlannerRuntime() {
  return useQuery({
    queryKey: modelControlKeys.runtime,
    queryFn: modelControlApi.runtime,
  });
}

export function useOllamaStatus() {
  return useQuery({
    queryKey: modelControlKeys.ollamaStatus,
    queryFn: modelControlApi.ollamaStatus,
  });
}

export function useOllamaModels() {
  return useQuery({
    queryKey: modelControlKeys.ollamaModels,
    queryFn: modelControlApi.ollamaModels,
  });
}

export function useSmallModelCatalog() {
  return useQuery({
    queryKey: modelControlKeys.catalog,
    queryFn: modelControlApi.catalog,
  });
}

export function useModelDownloads() {
  return useQuery({
    queryKey: modelControlKeys.downloads,
    queryFn: modelControlApi.downloads,
  });
}

export function useCreateModelProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.createProfile,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.profiles,
      });
    },
  });
}

export function useActivateModelProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.activateProfile,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.runtime,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.profiles,
      });
    },
  });
}

export function useStartModelDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.startDownload,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.downloads,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.ollamaModels,
      });
    },
  });
}

export function useActivateOllamaModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.activateOllamaModel,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.runtime,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.profiles,
      });
    },
  });
}

export function usePlannerDryRun() {
  return useMutation({ mutationFn: modelControlApi.dryRun });
}
