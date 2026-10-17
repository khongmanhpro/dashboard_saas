import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { NamedRef } from "./leads";

export type ConnectionStatus = "active" | "missing_permissions" | "disconnected";

export interface Bm {
  id: string;
  name: string;
  fb_business_id: string;
  verification_status: string | null;
  system_user_name: string | null;
  token_last4: string | null;
  status: ConnectionStatus;
  status_detail: string | null;
  missing_scopes: string[];
  page_count: number;
  ad_account_count: number;
  last_checked_at: string | null;
  is_mock: boolean;
}

export interface BmOverview {
  bms: Bm[];
  tracked_pages: number;
  unassigned_pages: number;
  ad_accounts: number;
  can_connect: boolean;
}

export interface CheckItem {
  key: "token_valid" | "pages" | "webhooks" | "ad_accounts" | "leadgen" | "other_scopes";
  level: "ok" | "warn" | "fail";
  count: number | null;
  total: number | null;
  detail: string | null;
}

export interface CheckResult {
  business_id: string;
  business_name: string;
  verification_status: string | null;
  system_user_name: string | null;
  scopes: string[];
  missing_scopes: string[];
  can_save: boolean;
  checks: CheckItem[];
  pages: { fb_page_id: string; name: string; state: "new" | "existing" | "other_workspace" }[];
  ad_account_count: number;
  already_connected: boolean;
}

export interface PageRow {
  id: string;
  fb_page_id: string;
  name: string;
  business_manager: string;
  is_tracked: boolean;
  untracked_reason: "other_workspace" | "removed_from_bm" | "bm_disconnected" | null;
  webhook_subscribed: boolean;
  owner: NamedRef | null;
  owner_since: string | null;
  leads_7d: number;
  is_new: boolean;
}

export interface TokenBody {
  token: string;
  fb_business_id?: string;
  name?: string;
}

const BM_KEY = ["bms"] as const;

export function useBms() {
  return useQuery({ queryKey: [...BM_KEY, "list"], queryFn: () => api<BmOverview>("/api/bms") });
}

export function usePages(enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...BM_KEY, "pages"],
    queryFn: () => api<{ pages: PageRow[]; candidates: NamedRef[]; one_page_per_member: boolean }>("/api/pages"),
  });
}

export function useCheckToken() {
  return useMutation({
    mutationFn: (body: TokenBody) => api<CheckResult>("/api/bms/check", { method: "POST", body }),
  });
}

function useBmMutation<T>(run: (body: T) => Promise<Bm>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: run, onSuccess: () => void client.invalidateQueries({ queryKey: BM_KEY }) });
}

export function useConnectBm() {
  return useBmMutation((body: TokenBody) => api<Bm>("/api/bms", { method: "POST", body }));
}

export function useRotateToken(bmId: string) {
  return useBmMutation((body: TokenBody) => api<Bm>(`/api/bms/${bmId}/token`, { method: "PUT", body }));
}

export function useBmAction() {
  return useBmMutation(({ id, action }: { id: string; action: "check" | "disconnect" }) =>
    api<Bm>(`/api/bms/${id}/${action}`, { method: "POST" }),
  );
}

export function useSetPageOwner() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, memberId }: { pageId: string; memberId: string | null }) =>
      api<void>(`/api/pages/${pageId}/owner`, { method: "PUT", body: { member_id: memberId } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: BM_KEY });
      void client.invalidateQueries({ queryKey: ["staff"] });
    },
  });
}

export interface ImportRow {
  row: number;
  full_name: string;
  email: string;
  team: string | null;
  role: string | null;
  page: string | null;
  action: "create" | "update" | null;
  errors: string[];
}

export interface ImportPreview {
  id: string;
  file_name: string;
  rows_total: number;
  rows_ok: number;
  rows_failed: number;
  rows: ImportRow[];
}

export async function previewImport(file: File): Promise<ImportPreview> {
  const { readCookie, CSRF_COOKIE, CSRF_HEADER, ApiError } = await import("./client");
  const headers: Record<string, string> = {
    "Content-Type": "application/octet-stream",
    "X-File-Name": encodeURIComponent(file.name),
  };
  const csrf = readCookie(CSRF_COOKIE);
  if (csrf) headers[CSRF_HEADER] = csrf;
  const response = await fetch("/api/imports/members/preview", {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: file,
  });
  const data = (await response.json().catch(() => null)) as { detail?: { code?: string } } | ImportPreview | null;
  if (!response.ok) {
    const code = data && "detail" in data && data.detail && typeof data.detail === "object" ? data.detail.code : undefined;
    throw new ApiError(response.status, code ?? (response.status === 413 ? "import_file_too_large" : "unknown"));
  }
  return data as ImportPreview;
}

export function useApplyImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<{ created: number; updated: number; skipped: number; credentials_file: string | null }>(
        `/api/imports/${id}/apply`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: BM_KEY });
      void client.invalidateQueries({ queryKey: ["staff"] });
      void client.invalidateQueries({ queryKey: ["members"] });
    },
  });
}

/** Tải file từ base64 ngay trên trình duyệt (file mật khẩu tạm không lưu trên máy chủ). */
export function downloadBase64(base64: string, fileName: string, type: string): void {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface Team {
  id: string;
  name: string;
}

export function useTeams(enabled: boolean) {
  return useQuery({ queryKey: ["members", "teams"], queryFn: () => api<Team[]>("/api/teams"), enabled });
}

export function useCreateMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; full_name: string; role: string; team_id: string | null; temp_password: string }) =>
      api<{ id: string }>("/api/members", { method: "POST", body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["members"] });
      void client.invalidateQueries({ queryKey: BM_KEY });
    },
  });
}
