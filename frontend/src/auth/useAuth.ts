import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";
import type { LoginResponse, Me, PublicConfig } from "../api/types";
import { disablePush } from "../mobile/push";

export const ME_KEY = ["me"] as const;

/** Người đang đăng nhập; `null` khi chưa đăng nhập hoặc phiên hết hạn. */
export function useMe() {
  return useQuery<Me | null>({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return await api<Me>("/api/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function usePublicConfig() {
  return useQuery<PublicConfig>({
    queryKey: ["config"],
    queryFn: () => api<PublicConfig>("/api/config"),
    staleTime: Infinity,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<LoginResponse>("/api/auth/login", { method: "POST", body }),
    onSuccess: (data) => {
      const { csrf_token: _csrf, ...me } = data;
      client.setQueryData(ME_KEY, me);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      // Máy này không nhận nhắc việc của người vừa đăng xuất nữa.
      await disablePush().catch(() => undefined);
      await api<void>("/api/auth/logout", { method: "POST" });
    },
    onSettled: () => {
      client.clear();
      client.setQueryData(ME_KEY, null);
    },
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<void>("/api/auth/change-password", { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ME_KEY }),
  });
}
