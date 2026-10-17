import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { NamedRef } from "./leads";
import type { PeriodType, Tier } from "./staff";

/** Decimal từ backend đến dạng chuỗi. */
type Num = string;

export type RangeKey = "today" | "7d" | "30d" | "90d" | "month" | "custom";

export interface RangeParams {
  range: RangeKey;
  from?: string;
  to?: string;
}

export interface Metric {
  value: Num | null;
  previous: Num | null;
}

export interface RangeOut {
  key: RangeKey;
  first_day: string;
  last_day: string;
}

export interface OverviewAlerts {
  overdue: number;
  overdue_pages: number;
  overdue_oldest_hours: number | null;
  slow_staff: number;
  slow_reply_minutes: number;
  unassigned_pages: number | null;
  bm_disconnected: number | null;
  bm_disconnected_name: string | null;
  bm_disconnected_pages: number;
  expensive_campaigns: number | null;
  unassigned_leads: number | null;
}

/** Phễu lồng nhau, kết quả tách riêng (docs/metrics.md). */
export interface Funnel {
  new: number;
  replied: number;
  unreplied: number;
  phone: number;
  no_phone: number;
  called: number;
  not_called: number;
  won: number;
  lost: number;
  callback: number;
  pending: number;
}

export interface BoardRow {
  member: NamedRef;
  rank: number | null;
  total: Num | null;
  tier: Tier | null;
  page: string | null;
  note_key: string | null;
  note_value: Num | null;
}

export interface Overview {
  range: RangeOut;
  members: number;
  pages: number;
  bms: number;
  alerts: OverviewAlerts;
  kpis: {
    new_leads: Metric;
    median_response_seconds: Metric;
    phone_rate: Metric;
    close_rate: Metric;
    revenue_vnd: Metric;
    cost_per_won_vnd: Metric | null;
    overdue_in_range: number;
  };
  funnel: Funnel;
  daily: { day: string; new: number; won: number }[];
  campaigns: {
    id: string;
    name: string;
    spend_vnd: number | null;
    leads: number;
    won: number;
    cost_per_won_vnd: number | null;
  }[] | null;
  missing_fx: string[];
  boards: {
    period: PeriodType;
    first_day: string;
    last_day: string;
    same_as_range: boolean;
    top: BoardRow[];
    bottom: BoardRow[];
  };
  teams: NamedRef[];
  is_mock: boolean;
}

export type PageStatus = "ok" | "declining" | "disconnected";
export type PageTab = "all" | "unassigned" | "low_posts" | "declining" | "disconnected";
export type PageSort = "leads" | "score" | "posts" | "name";
export const PAGE_TABS: PageTab[] = ["all", "unassigned", "low_posts", "declining", "disconnected"];
export const PAGE_SORTS: PageSort[] = ["leads", "score", "posts", "name"];

export interface PageReportRow {
  id: string;
  name: string;
  fb_page_id: string;
  bm_name: string;
  owner: NamedRef | null;
  owner_total: Num | null;
  owner_tier: Tier | null;
  /** Chỉ có khi khách của Trang trong kỳ thuộc hơn một người (null = chưa có người phụ trách). */
  owners_in_range: { member: NamedRef | null; leads: number }[];
  leads_7d: number;
  median_response_seconds: number | null;
  won_7d: number;
  revenue_7d: number;
  overdue_7d: number;
  posts_week: number | null;
  views_30d: number | null;
  views_daily: (number | null)[];
  status: PageStatus;
}

export interface PageReportList {
  rows: PageReportRow[];
  total: number;
  page: number;
  page_size: number;
  tabs: Record<PageTab, number>;
  bms: NamedRef[];
  teams: NamedRef[];
  posts_target: number;
  can_assign: boolean;
  range: RangeOut;
  is_mock: boolean;
}

export interface PageQuery {
  tab: PageTab;
  q: string;
  bm_id: string;
  team_id: string;
  sort: PageSort;
  page: number;
}

export interface PostRow {
  id: string;
  excerpt: string | null;
  created_time: string;
  type: string;
  views: number | null;
  reactions: number;
  comments: number;
  shares: number;
  engagement_rate: Num | null;
  permalink: string | null;
}

export interface PageDetail {
  id: string;
  name: string;
  fb_page_id: string;
  bm_name: string;
  status: PageStatus;
  owner: NamedRef | null;
  team: string | null;
  content_synced_at: string | null;
  kpis: {
    followers: number | null;
    new_follows: Metric;
    views: Metric;
    reach: Metric;
    engagements: Metric;
    video_views: Metric;
    posts: Metric;
  };
  daily_views: { day: string; value: number | null }[];
  heatmap: (Num | null)[][] | null;
  heatmap_min_posts: number;
  posts: PostRow[];
  is_mock: boolean;
}

export type AdsLevel = "campaign" | "adset" | "ad";
export const ADS_LEVELS: AdsLevel[] = ["campaign", "adset", "ad"];

export interface AdsRow {
  id: string;
  name: string;
  parent: string | null;
  account: string;
  objective: string | null;
  status: string | null;
  daily_budget_vnd: number | null;
  spend_vnd: number | null;
  results: number | null;
  cost_per_result_vnd: number | null;
  ctr: Num | null;
  cpm_vnd: number | null;
  frequency: Num | null;
  leads: number;
  won: number;
  cost_per_won_vnd: number | null;
}

export interface AdsReport {
  range: RangeOut;
  accounts: { id: string; name: string; currency: string | null }[];
  kpis: Record<
    | "spend_vnd"
    | "results"
    | "cost_per_result_vnd"
    | "ctr"
    | "cpm_vnd"
    | "frequency"
    | "leads"
    | "won"
    | "cost_per_won_vnd",
    Metric
  >;
  cost_bars: { id: string; name: string; cost_per_result_vnd: number }[];
  cost_threshold_vnd: number;
  rows: AdsRow[];
  missing_fx: string[];
  is_mock: boolean;
}

export type RuleType = "bm_status" | "cost_per_result" | "cost_per_won" | "frequency" | "daily_summary";
export const RULE_TYPES: RuleType[] = ["bm_status", "cost_per_result", "cost_per_won", "frequency", "daily_summary"];

export interface AlertRule {
  type: RuleType;
  enabled: boolean;
  params: Record<string, number>;
}

export interface RulesView {
  rules: AlertRule[];
  can_edit: boolean;
  chat_configured: boolean;
}

export interface FxRate {
  id: string;
  currency: string;
  effective_from: string;
  vnd_per_unit: Num;
}

export interface AlertSettings {
  chat_id: string | null;
  bot_configured: boolean;
  is_mock: boolean;
  rules: AlertRule[];
  fx_rates: FxRate[];
  currencies: string[];
  deliveries: { rule_type: RuleType; status: "sent" | "failed" | "mock"; error: string | null; sent_at: string }[];
}

export function rangeQuery(r: RangeParams): string {
  const params = new URLSearchParams({ range: r.range });
  if (r.range === "custom" && r.from && r.to) {
    params.set("from", r.from);
    params.set("to", r.to);
  }
  return params.toString();
}

const KEY = ["reports"] as const;

export function useOverview(r: RangeParams, teamId: string) {
  const query = rangeQuery(r) + (teamId ? `&team_id=${encodeURIComponent(teamId)}` : "");
  return useQuery({
    queryKey: [...KEY, "overview", query],
    queryFn: () => api<Overview>(`/api/reports/overview?${query}`),
    placeholderData: keepPreviousData,
    enabled: r.range !== "custom" || Boolean(r.from && r.to),
  });
}

export function overviewExportUrl(r: RangeParams, teamId: string): string {
  return `/api/reports/overview.xlsx?${rangeQuery(r)}${teamId ? `&team_id=${encodeURIComponent(teamId)}` : ""}`;
}

export function pageQueryString(q: PageQuery): string {
  const params = new URLSearchParams({ tab: q.tab, sort: q.sort, page: String(q.page) });
  if (q.q.trim()) params.set("q", q.q.trim());
  if (q.bm_id) params.set("bm_id", q.bm_id);
  if (q.team_id) params.set("team_id", q.team_id);
  return params.toString();
}

export function usePageReport(q: PageQuery) {
  const query = pageQueryString(q);
  return useQuery({
    queryKey: [...KEY, "pages", query],
    queryFn: () => api<PageReportList>(`/api/reports/pages?${query}`),
    placeholderData: keepPreviousData,
  });
}

export function usePageDetail(id: string) {
  return useQuery({
    queryKey: [...KEY, "page", id],
    queryFn: () => api<PageDetail>(`/api/reports/pages/${id}`),
    retry: false,
  });
}

export function useAdsReport(r: RangeParams, level: AdsLevel, accountId: string) {
  const query = `${rangeQuery(r)}&level=${level}${accountId ? `&account_id=${encodeURIComponent(accountId)}` : ""}`;
  return useQuery({
    queryKey: [...KEY, "ads", query],
    queryFn: () => api<AdsReport>(`/api/reports/ads?${query}`),
    placeholderData: keepPreviousData,
    enabled: r.range !== "custom" || Boolean(r.from && r.to),
  });
}

export function useAlertRules() {
  return useQuery({ queryKey: ["alerts", "rules"], queryFn: () => api<RulesView>("/api/alerts/rules") });
}

export function useToggleRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ type, enabled }: { type: RuleType; enabled: boolean }) =>
      api<RulesView>(`/api/alerts/rules/${type}`, { method: "PUT", body: { enabled } }),
    onSuccess: (view) => {
      client.setQueryData(["alerts", "rules"], view);
      void client.invalidateQueries({ queryKey: ["alerts", "settings"] });
    },
  });
}

export function useAlertSettings(enabled: boolean) {
  return useQuery({
    queryKey: ["alerts", "settings"],
    queryFn: () => api<AlertSettings>("/api/settings/alerts"),
    enabled,
  });
}

function useAlertMutation<T>(fn: (body: T) => Promise<AlertSettings>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (settings) => {
      client.setQueryData(["alerts", "settings"], settings);
      void client.invalidateQueries({ queryKey: ["alerts", "rules"] });
      void client.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useSaveAlertSettings() {
  return useAlertMutation((body: { chat_id: string | null; rules: AlertRule[] }) =>
    api<AlertSettings>("/api/settings/alerts", { method: "PUT", body }),
  );
}

export function useAddFxRate() {
  return useAlertMutation((body: { currency: string; effective_from: string; vnd_per_unit: string }) =>
    api<AlertSettings>("/api/settings/fx-rates", { method: "POST", body }),
  );
}

export function useDeleteFxRate() {
  return useAlertMutation((id: string) => api<AlertSettings>(`/api/settings/fx-rates/${id}`, { method: "DELETE" }));
}

export function useSendTestAlert() {
  return useMutation({
    mutationFn: () => api<{ status: string }>("/api/settings/alerts/test", { method: "POST" }),
  });
}
