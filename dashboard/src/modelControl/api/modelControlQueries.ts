// 模型控制中心的 React Query 边界。
//
// 这里集中定义浏览器侧缓存键和失效规则：API key 只在提交表单时经过
// modelControlApi 写入请求体，不进入 Query cache；profile、runtime、Ollama
// 模型列表和下载任务都以后端状态为准，mutation 成功后主动失效相关缓存，避免
// 页面显示旧的 active planner 或误把未安装模型显示为可用。
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
      // 新建 profile 后只刷新非敏感 profile 列表；secret 明文不会被缓存。
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
      // 激活 profile 会同时改变运行时快照和列表中的 active 标记。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.runtime,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.profiles,
      });
    },
  });
}

export function useTestModelProfile() {
  return useMutation({ mutationFn: modelControlApi.testProfile });
}

export function useReloadPlannerRuntime() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.reloadRuntime,
    onSuccess: () => {
      // reload 只刷新脱敏 runtime 状态，不触碰 secret 或硬件。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.runtime,
      });
    },
  });
}

export function useStartModelDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.startDownload,
    onSuccess: () => {
      // 下载完成与否由后端/Ollama tags 决定；下载任务和已安装模型都需要重取。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.downloads,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.ollamaModels,
      });
    },
  });
}

export function useCancelModelDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.cancelDownload,
    onSuccess: () => {
      // 取消是 best-effort 状态更新；下载任务列表需要重取以展示最终结果。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.downloads,
      });
    },
  });
}

export function useActivateOllamaModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.activateOllamaModel,
    onSuccess: () => {
      // 本地模型激活会创建/切换 OLLAMA profile，因此刷新 runtime 和 profile 列表。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.runtime,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.profiles,
      });
    },
  });
}

export function useDeleteOllamaModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: modelControlApi.deleteOllamaModel,
    onSuccess: () => {
      // 删除模型后刷新本地模型和目录 installed 标记。
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.ollamaModels,
      });
      void queryClient.invalidateQueries({
        queryKey: modelControlKeys.catalog,
      });
    },
  });
}

export function usePlannerDryRun() {
  return useMutation({ mutationFn: modelControlApi.dryRun });
}
