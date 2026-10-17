import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";

export type LeadStatus = "new" | "contacted" | "callback" | "won" | "lost";
export type LostReason = "price" | "out_of_area" | "no_answer" | "bought_elsewhere" | "other";
export type Period = "today" | "7d" | "30d" | "all";
export type Chip = "unreplied" | "overdue" | "phone_not_called" | "new_today";
export type SourceFilter = "ad" | "organic" | "form";

export const LEAD_STATUSES: LeadStatus[] = ["new", "contacted", "callback", "won", "lost"];
export const LOST_REASONS: LostReason[] = ["price", "out_of_area", "no_answer", "bought_elsewhere", "other"];

export interface NamedRef {
  id: string;
  name: string;
}

export interface LeadCard {
  id: string;
  display_name: string | null;
  short_ref: string;
  page: NamedRef;
  owner: NamedRef | null;
  source: "message" | "leadgen";
  from_ad: boolean;
  fb_ad_id: string | null;
  status: LeadStatus;
  first_inbound_at: string;
  first_reply_at: string | null;
  response_business_seconds: number | null;
  waiting_business_seconds: number | null;
  is_slow: boolean;
  result_due_at: string;
  result_at: string | null;
  overdue: boolean;
  callback_at: string | null;
  won_value_vnd: number | null;
  lost_reason: LostReason | null;
  phone: string | null;
  phone_masked: boolean;
  called_at: string | null;
}

export interface LeadPage {
  items: LeadCard[];
  next_cursor: string | null;
}

export interface LeadSummary {
  total: number;
  unreplied: number;
  overdue: number;
  phone_not_called: number;
  new_today: number;
  by_status: Record<LeadStatus, number>;
}

export interface TimelineItem {
  kind: "message" | "event";
  at: string;
  direction: "in" | "out" | null;
  text: string | null;
  has_attachments: boolean;
  is_automated: boolean;
  is_first_reply: boolean;
  type: string | null;
  actor: string | null;
  data: Record<string, unknown> | null;
}

export interface LeadDetail extends LeadCard {
  fb_page_id: string;
  slow_reply_minutes: number;
  lost_note: string | null;
  phones: string[];
  timeline: TimelineItem[];
  timeline_truncated: boolean;
  permissions: { can_update: boolean; can_edit_result: boolean; edit_until: string | null };
}

export interface LeadFilters {
  period: Period;
  chip?: Chip;
  page_id?: string;
  owner_id?: string;
  source?: SourceFilter;
  q?: string;
}

export interface ResultBody {
  status: "callback" | "won" | "lost";
  callback_at?: string;
  won_value_vnd?: number;
  lost_reason?: LostReason;
  note?: string;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const LEADS_KEY = ["leads"] as const;

export function useLeadSummary(filters: LeadFilters, enabled = true) {
  return useQuery({
    queryKey: [...LEADS_KEY, "summary", filters],
    queryFn: () => api<LeadSummary>(`/api/leads/summary${query({ ...filters })}`),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useLeadList(filters: LeadFilters, status: LeadStatus | undefined, pageSize: number) {
  return useInfiniteQuery({
    queryKey: [...LEADS_KEY, "list", filters, status ?? "all", pageSize],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api<LeadPage>(`/api/leads${query({ ...filters, status, limit: pageSize, cursor: pageParam })}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useFilterOptions() {
  return useQuery({
    queryKey: [...LEADS_KEY, "filter-options"],
    queryFn: () => api<{ pages: NamedRef[]; owners: NamedRef[] }>("/api/leads/filter-options"),
    staleTime: 60_000,
  });
}

export function useLead(id: string) {
  return useQuery({
    queryKey: [...LEADS_KEY, "detail", id],
    queryFn: () => api<LeadDetail>(`/api/leads/${id}`),
    retry: false,
  });
}

function useLeadMutation<TBody>(id: string, run: (body: TBody) => Promise<LeadDetail>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (detail) => {
      client.setQueryData([...LEADS_KEY, "detail", id], detail);
      // Danh sách, số đếm và số trên menu đều phải đổi theo.
      void client.invalidateQueries({ queryKey: LEADS_KEY, refetchType: "active" });
    },
  });
}

export function useSetCalled(id: string) {
  return useLeadMutation(id, (called: boolean) =>
    api<LeadDetail>(`/api/leads/${id}/called`, { method: "POST", body: { called } }),
  );
}

export function useSetResult(id: string) {
  return useLeadMutation(id, (body: ResultBody) =>
    api<LeadDetail>(`/api/leads/${id}/result`, { method: "PUT", body }),
  );
}
