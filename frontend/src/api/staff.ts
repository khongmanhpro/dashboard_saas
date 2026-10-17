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

// Số thập phân từ backend (Decimal) đến dưới dạng chuỗi.
type Num = string;

export interface PeriodInfo {
  type: PeriodType;
  first_day: string | null;
  last_day: string | null;
  computed_at: string | null;
  is_final: boolean;
}

export interface LeaderboardRow {
  member: NamedRef;
  team: NamedRef | null;
  pages: string[];
  is_self: boolean;
  rank: number | null;
  tier: Tier | null;
  insufficient_data: boolean;
  total: Num | null;
  delta: Num | null;
  lead_count: number | null;
  median_response_seconds: number | null;
  phone_rate: Num | null;
  close_rate: Num | null;
  revenue_vnd: number | null;
  overdue_count: number | null;
}

export interface Leaderboard {
  period: PeriodInfo;
  min_leads: number;
  tiers: Record<Tier, number> | null;
  insufficient_count: number | null;
  kpis: {
    lead_count: number;
    median_response_seconds: number | null;
    phone_rate: Num | null;
    close_rate: Num | null;
    revenue_vnd: number;
    overdue_count: number;
  } | null;
  teams: NamedRef[];
  rows: LeaderboardRow[];
  full_view: boolean;
}

export interface ScorePart {
  key: Criterion;
  weight: number;
  effective_weight: Num | null;
  score: Num | null;
  points: Num | null;
  raw: Record<string, number | Num | null>;
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
  trend: { first_day: string; total: Num | null; tier: Tier | null }[];
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

export function usePreview(weights: Weights, enabled: boolean) {
  return useQuery({
    queryKey: [...STAFF_KEY, "preview", weights],
    queryFn: () => api<{ rows: PreviewRow[] }>("/api/score/preview", { method: "POST", body: weights }),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useSaveFormula() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (weights: Weights) => api<Formula>("/api/score/formula", { method: "PUT", body: { weights } }),
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
