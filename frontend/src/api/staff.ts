import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { LeadStatus, NamedRef } from "./leads";

export type PeriodType = "week" | "rolling_7" | "rolling_30" | "month";
export type Tier = "A" | "B" | "C" | "D";
export type Criterion = "close_rate" | "response_speed" | "revenue" | "phone_rate" | "page_care" | "on_time";

export const PERIOD_TYPES: PeriodType[] = ["week", "rolling_7", "rolling_30", "month"];
export const TIERS: Tier[] = ["A", "B", "C", "D"];
export const CRITERIA: Criterion[] = ["close_rate", "response_speed", "revenue", "phone_rate", "page_care", "on_time"];

export type Weights = Record<Criterion, number>;
export const DEFAULT_WEIGHTS: Weights = {
  close_rate: 30,
  response_speed: 25,
  revenue: 20,
  phone_rate: 10,
  page_care: 10,
  on_time: 5,
};

/** Ngưỡng tuyệt đối (decisions.md mục K): tỉ lệ bằng phần trăm, doanh thu là mức 100 điểm mỗi tuần. */
export interface Thresholds {
  speed_full_minutes: number;
  speed_zero_minutes: number;
  close_rate_zero: number;
  close_rate_full: number;
  revenue_full_vnd: number;
  phone_rate_zero: number;
  phone_rate_full: number;
  on_time_zero: number;
  on_time_full: number;
}

export const DEFAULT_THRESHOLDS: Thresholds = {
  speed_full_minutes: 5,
  speed_zero_minutes: 120,
  close_rate_zero: 5,
  close_rate_full: 30,
  revenue_full_vnd: 20_000_000,
  phone_rate_zero: 30,
  phone_rate_full: 80,
  on_time_zero: 50,
  on_time_full: 95,
};

export interface FormulaBody {
  weights: Weights;
  thresholds: Thresholds;
}

// Số thập phân từ backend (Decimal) đến dưới dạng chuỗi.
type Num = string;

export interface PeriodInfo {
  type: PeriodType;
  first_day: string | null;
  last_day: string | null;
  computed_at: string | null;
  is_final: boolean;
}

export type MemberRole = "owner" | "manager" | "team_lead" | "staff" | "viewer";

export interface LeaderboardRow {
  member: NamedRef;
  role: MemberRole | null;
  team: NamedRef | null;
  pages: string[];
  /** Lượt phụ trách Trang đã kết thúc trong kỳ. */
  past_pages: { name: string; until: string }[];
  is_self: boolean;
  rank: number | null;
  tier: Tier | null;
  insufficient_data: boolean;
  total: Num | null;
  delta: Num | null;
  /** Tuần trước tính bằng phiên bản công thức khác: ▲▼ chỉ để tham khảo. */
  delta_other_formula: boolean;
  lead_count: number | null;
  won_count: number | null;
  median_response_seconds: number | null;
  phone_rate: Num | null;
  close_rate: Num | null;
  revenue_vnd: number | null;
  overdue_count: number | null;
}

/** Khách vào Trang lúc chưa có người phụ trách: không xếp hạng, không tính điểm. */
export interface UnassignedRow {
  lead_count: number;
  won_count: number;
  median_response_seconds: number | null;
  phone_rate: Num | null;
  close_rate: Num | null;
  revenue_vnd: number;
  overdue_count: number;
}

export interface Leaderboard {
  period: PeriodInfo;
  min_leads: number;
  tiers: Record<Tier, number> | null;
  insufficient_count: number | null;
  kpis: {
    lead_count: number;
    won_count: number;
    median_response_seconds: number | null;
    phone_rate: Num | null;
    close_rate: Num | null;
    revenue_vnd: number;
    overdue_count: number;
  } | null;
  teams: NamedRef[];
  rows: LeaderboardRow[];
  unassigned: UnassignedRow | null;
  full_view: boolean;
}

export interface ScorePart {
  key: Criterion;
  weight: number;
  effective_weight: Num | null;
  score: Num | null;
  points: Num | null;
  raw: Record<string, number | Num | null>;
  /** linear: ngưỡng tuyệt đối (zero = 0 điểm, full = 100 điểm); target: mục tiêu bài. */
  method: "linear" | "target";
  zero: Num | null;
  full: Num | null;
}

export interface StaffDetail {
  member: NamedRef;
  role: string;
  team: NamedRef | null;
  team_lead: string | null;
  pages: { id: string; name: string; since: string }[];
  period: PeriodInfo;
  total: Num | null;
  tier: Tier | null;
  rank: number | null;
  ranked_count: number;
  delta: Num | null;
  insufficient_data: boolean;
  min_leads: number;
  lead_count: number;
  parts: ScorePart[];
  funnel: { key: "leads" | "replied" | "phone" | "called" | "won"; value: number; rate: Num | null; company_rate: Num | null }[];
  hours: { label: string; median_minutes: Num | null; count: number }[];
  trend: {
    first_day: string;
    total: Num | null;
    tier: Tier | null;
    is_final: boolean;
    formula_version: number | null;
    other_formula: boolean;
  }[];
  delta_other_formula: boolean;
  formula_version: number;
  speed_full_minutes: number;
  speed_zero_minutes: number;
  posts_target: Num | null;
  recent: {
    id: string;
    display_name: string | null;
    short_ref: string;
    first_inbound_at: string;
    response_business_seconds: number | null;
    status: LeadStatus;
    overdue: boolean;
  }[];
  slow_reply_minutes: number;
}

export interface Formula {
  version: number;
  weights: Weights;
  speed_full_minutes: number;
  speed_zero_minutes: number;
  tier_a: number;
  tier_b: number;
  tier_c: number;
  min_leads: number;
  posts_per_week_target: number;
  thresholds: Thresholds;
  score_method: "percentile" | "threshold";
  effective_from: string;
  created_by: string | null;
  page_care_available: boolean;
  can_edit: boolean;
}

export interface PreviewRow {
  member: NamedRef;
  current_total: Num | null;
  current_tier: Tier | null;
  new_total: Num | null;
  new_tier: Tier | null;
  new_rank: number | null;
}

const STAFF_KEY = ["staff"] as const;

export function useLeaderboard(period: PeriodType) {
  return useQuery({
    queryKey: [...STAFF_KEY, "leaderboard", period],
    queryFn: () => api<Leaderboard>(`/api/staff/leaderboard?period=${period}`),
    placeholderData: keepPreviousData,
  });
}

export function useStaffDetail(id: string, period: PeriodType) {
  return useQuery({
    queryKey: [...STAFF_KEY, "detail", id, period],
    queryFn: () => api<StaffDetail>(`/api/staff/${id}?period=${period}`),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useFormula() {
  return useQuery({ queryKey: [...STAFF_KEY, "formula"], queryFn: () => api<Formula>("/api/score/formula") });
}

export function usePreview(body: FormulaBody, enabled: boolean) {
  return useQuery({
    queryKey: [...STAFF_KEY, "preview", body],
    queryFn: () => api<{ rows: PreviewRow[] }>("/api/score/preview", { method: "POST", body }),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useSaveFormula() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: FormulaBody) => api<Formula>("/api/score/formula", { method: "PUT", body }),
    onSuccess: (formula) => {
      client.setQueryData([...STAFF_KEY, "formula"], formula);
      void client.invalidateQueries({ queryKey: STAFF_KEY });
    },
  });
}

export function useRecompute() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<Record<string, number>>("/api/score/recompute", { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: STAFF_KEY }),
  });
}
