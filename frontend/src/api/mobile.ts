import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import { LEADS_KEY, type LeadCard } from "./leads";
import type { Tier } from "./staff";

export type MobileTab = "todo" | "callback" | "done";
export const MOBILE_TABS: MobileTab[] = ["todo", "callback", "done"];

export interface MobileHome {
  first_name: string;
  pages: string[];
  score: {
    total: string | null;
    tier: Tier | null;
    rank: number | null;
    ranked_count: number;
    rank_change: number | null;
    next_tier: Tier | null;
    points_to_next: string | null;
    insufficient_data: boolean;
    lead_count: number;
    min_leads: number;
  } | null;
  stats: { median_response_seconds: number | null; phone_rate: string | null; close_rate: string | null } | null;
  phone_not_called: number;
  tabs: Record<MobileTab, number>;
  unread: number;
}

export interface MobileLead extends LeadCard {
  fb_page_id: string;
  snippet: string | null;
  phone_captured_at: string | null;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  lead_id: string | null;
  created_at: string;
  read_at: string | null;
}

// Dưới khóa "leads" để mọi cập nhật khách (đã gọi, kết quả) tự làm mới cả màn hình điện thoại.
const MOBILE_KEY = [...LEADS_KEY, "mobile"] as const;
const NOTIFY_KEY = [...LEADS_KEY, "notifications"] as const;

export function useMobileHome() {
  return useQuery({ queryKey: [...MOBILE_KEY, "home"], queryFn: () => api<MobileHome>("/api/m/home") });
}

export function useMobileLeads(tab: MobileTab) {
  return useQuery({
    queryKey: [...MOBILE_KEY, "list", tab],
    queryFn: () => api<MobileLead[]>(`/api/m/leads?tab=${tab}`),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: NOTIFY_KEY,
    queryFn: () => api<{ items: NotificationItem[]; unread: number }>("/api/notifications"),
  });
}

export function useMarkRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number | "all") =>
      api<void>(id === "all" ? "/api/notifications/read-all" : `/api/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: LEADS_KEY }),
  });
}

export function useRemind(leadId: string) {
  return useMutation({
    mutationFn: () => api<void>(`/api/leads/${leadId}/remind`, { method: "POST" }),
  });
}
