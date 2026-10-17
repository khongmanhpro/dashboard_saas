import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { usePages, useSetPageOwner } from "../../api/bms";
import {
  PAGE_SORTS,
  PAGE_TABS,
  usePageReport,
  type PageQuery,
  type PageReportRow,
  type PageSort,
  type PageStatus,
  type PageTab,
} from "../../api/reports";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDuration } from "../../leads/format";
import { formatCount, formatNumber, linePoints, shortDate, trendOf } from "../../reports/format";
import { formatScore } from "../../staff/format";
import { TierBadge } from "../staff/StaffPage";
import { StatusPill } from "./common";

const STATUS_TONE: Record<PageStatus, "good" | "bad" | "warn"> = { ok: "good", declining: "bad", disconnected: "warn" };
const SLOW_SECONDS = 30 * 60;

function readTab(value: string | null): PageTab {
  return PAGE_TABS.find((tab) => tab === value) ?? "all";
}

function PostsMeter({ posts, target }: { posts: number | null; target: number }) {
  if (posts === null) return <span className="muted">{t.pages.noPosts}</span>;
  const tone = posts >= target ? "good" : posts >= 3 ? "warn" : "bad";
  const slots = Math.max(target, 1);
  return (
    <span className={`posts-meter posts-meter--${tone}`}>
      <span className="posts-meter__bars" aria-hidden="true">
        {Array.from({ length: slots }, (_, i) => (
          <i key={i} className={i < posts ? "on" : undefined} />
        ))}
      </span>
      <b>{format(t.pages.postsOf, { n: posts, target })}</b>
    </span>
  );
}

function Spark({ row }: { row: PageReportRow }) {
  const trend = row.status === "disconnected" ? "none" : trendOf(row.views_daily);
  const points = trend === "none" ? "2,12 94,12" : linePoints(row.views_daily, 96, 24);
  return (
    <span className="spark-cell">
      {formatCount(row.views_30d)}
      <svg className={`spark spark--${trend}`} role="img" aria-label={t.pages.trend[trend]} width="64" height="24" viewBox="0 0 96 24">
        <polyline points={points} />
      </svg>
    </span>
  );
}

function Shares({ row }: { row: PageReportRow }) {
  if (row.owners_in_range.length === 0) return null;
  return (
    <span className="owner-shares" data-testid="owner-shares">
      {t.pages.sharesLabel}{" "}
      {row.owners_in_range
        .map((s) => format(t.pages.share, { name: s.member?.name ?? t.pages.shareUnassigned, n: s.leads }))
        .join(" · ")}
    </span>
  );
}

function OwnerCell({
  row,
  canAssign,
  candidates,
  onAssign,
  busy,
}: {
  row: PageReportRow;
  canAssign: boolean;
  candidates: { id: string; name: string }[];
  onAssign: (memberId: string) => void;
  busy: boolean;
}) {
  if (row.owner) {
    return (
      <Link to={`/staff/${row.owner.id}`} className="owner-cell">
        <TierBadge tier={row.owner_tier} />
        <span className="page-cell__text">
          <span>{row.owner.name}</span>
          <span className="page-cell__sub">
            {row.owner_total !== null ? format(t.pages.points, { n: formatScore(row.owner_total) }) : t.pages.noScore}
          </span>
        </span>
      </Link>
    );
  }
  if (!canAssign) return <span className="muted">{t.pages.noOwner}</span>;
  return (
    <select
      className="assign-select"
      aria-label={format(t.pages.assignLabel, { name: row.name })}
      value=""
      disabled={busy}
      onChange={(e) => e.target.value && onAssign(e.target.value)}
    >
      <option value="">{t.pages.choose}</option>
      {candidates.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

export function PagesPage() {
  const me = useOutletContext<Me>();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState<PageQuery>({
    tab: readTab(params.get("tab")),
    q: "",
    bm_id: "",
    team_id: "",
    sort: "leads",
    page: 1,
  });
  const [search, setSearch] = useState("");
  useEffect(() => {
    const id = setTimeout(() => setQuery((q) => (q.q === search ? q : { ...q, q: search, page: 1 })), 300);
    return () => clearTimeout(id);
  }, [search]);
  const report = usePageReport(query);
  const data = report.data;
  const canAssign = Boolean(data?.can_assign);
  const candidates = usePages(canAssign);
  const setOwner = useSetPageOwner();
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);

  const update = (patch: Partial<PageQuery>) => setQuery((q) => ({ ...q, ...patch, page: patch.page ?? 1 }));
  const pickTab = (tab: PageTab) => {
    update({ tab });
    setParams(tab === "all" ? {} : { tab }, { replace: true });
  };
  const assign = (pageId: string, memberId: string) => {
    setNotice(null);
    setOwner.mutate(
      { pageId, memberId },
      {
        onSuccess: () => {
          setNotice(t.pages.assigned);
          void client.invalidateQueries({ queryKey: ["reports"] });
        },
        onError: (e) => setNotice(e instanceof ApiError ? errorMessage(e.code) : t.errors.unknown),
      },
    );
  };

  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? 20;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (query.page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, query.page * pageSize);
  const canBm = "bm.view" in me.permissions;
  const canImport = "member.manage" in me.permissions;

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.pages.title} />
          {data ? (
            <div className="page-sub">
              {format(t.pages.subtitle, {
                n: data.tabs.all,
                target: data.posts_target,
                from: shortDate(data.range.first_day),
                to: shortDate(data.range.last_day),
              })}
            </div>
          ) : null}
        </div>
        <div className="row-actions">
          <a className="btn btn--link" href="/api/reports/pages.xlsx" download>
            {t.reports.exportExcel}
          </a>
          {canImport ? (
            <Link className="btn btn--link" to="/staff?import=1">
              {t.pages.assignExcel}
            </Link>
          ) : null}
          {canBm ? (
            <Link className="btn btn--primary btn--link" to="/bm">
              {t.pages.addFromBm}
            </Link>
          ) : null}
        </div>
      </div>

      <div className="chips" role="tablist" aria-label={t.pages.tabsLabel}>
        {PAGE_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={query.tab === tab}
            aria-pressed={query.tab === tab}
            className={tab === "unassigned" ? "chip chip--bad" : "chip"}
            onClick={() => pickTab(tab)}
            data-testid={`pages-tab-${tab}`}
          >
            {t.pages.tabs[tab]} <b>{data?.tabs[tab] ?? ""}</b>
          </button>
        ))}
      </div>

      <div className="filter-bar" role="search">
        <label className="search-box">
          <span className="sr-only">{t.pages.search}</span>
          <input
            type="search"
            value={search}
            placeholder={t.pages.searchPlaceholder}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {data && data.bms.length > 1 ? (
          <label className="report-select">
            {t.pages.bm}
            <select value={query.bm_id} onChange={(e) => update({ bm_id: e.target.value })}>
              <option value="">{t.pages.allBms}</option>
              {data.bms.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {data && data.teams.length > 1 ? (
          <label className="report-select">
            {t.reports.team}
            <select value={query.team_id} onChange={(e) => update({ team_id: e.target.value })}>
              <option value="">{t.reports.allTeams}</option>
              {data.teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="report-select">
          {t.pages.sort}
          <select value={query.sort} onChange={(e) => update({ sort: e.target.value as PageSort })}>
            {PAGE_SORTS.map((s) => (
              <option key={s} value={s}>
                {t.pages.sorts[s]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {notice ? <div className="notice notice--info" role="status">{notice}</div> : null}
      {report.error instanceof ApiError ? <div className="alert alert--error">{errorMessage(report.error.code)}</div> : null}

      <div className="table-wrap">
        <table data-testid="pages-table">
          <thead>
            <tr>
              <th scope="col">{t.pages.cols.page}</th>
              <th scope="col">{t.pages.cols.owner}</th>
              <th scope="col" className="num">{t.pages.cols.leads}</th>
              <th scope="col" className="num">{t.pages.cols.response}</th>
              <th scope="col" className="num">{t.pages.cols.won}</th>
              <th scope="col">{t.pages.cols.posts}</th>
              <th scope="col" className="num">{t.pages.cols.views}</th>
              <th scope="col">{t.pages.cols.status}</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows ?? []).map((row) => (
              <tr key={row.id} data-testid="page-row">
                <td>
                  <Link to={`/pages/${row.id}`} className="page-cell">
                    <span className="page-cell__avatar" aria-hidden="true">
                      {row.name.replace("[", "").slice(0, 1).toUpperCase()}
                    </span>
                    <span className="page-cell__text">
                      <span className="page-cell__name">{row.name}</span>
                      <span className="page-cell__sub">{row.bm_name}</span>
                    </span>
                  </Link>
                </td>
                <td>
                  <OwnerCell
                    row={row}
                    canAssign={canAssign}
                    candidates={candidates.data?.candidates ?? []}
                    onAssign={(memberId) => assign(row.id, memberId)}
                    busy={setOwner.isPending}
                  />
                  <Shares row={row} />
                </td>
                <td className="num">
                  <b>{formatNumber(row.leads_7d)}</b>
                </td>
                <td className={row.median_response_seconds !== null && row.median_response_seconds > SLOW_SECONDS ? "num cell--bad" : "num"}>
                  {row.median_response_seconds === null ? "–" : formatDuration(row.median_response_seconds)}
                </td>
                <td className="num">{formatNumber(row.won_7d)}</td>
                <td>
                  <PostsMeter posts={row.posts_week} target={data?.posts_target ?? 5} />
                </td>
                <td className="num">
                  <Spark row={row} />
                </td>
                <td>
                  <StatusPill tone={STATUS_TONE[row.status]}>{t.pages.status[row.status]}</StatusPill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.rows.length === 0 ? <p className="muted" style={{ padding: 16 }}>{t.pages.empty}</p> : null}
      </div>

      <div className="table-foot">
        <span>{format(t.pages.showing, { from, to, total })}</span>
        <div className="pager">
          <button type="button" aria-label={t.pages.prev} disabled={query.page <= 1} onClick={() => update({ page: query.page - 1 })}>
            ‹
          </button>
          {Array.from({ length: Math.min(pages, 7) }, (_, i) => i + 1).map((n) => (
            <button key={n} type="button" aria-current={n === query.page ? "page" : undefined} onClick={() => update({ page: n })}>
              {n}
            </button>
          ))}
          <button type="button" aria-label={t.pages.next} disabled={query.page >= pages} onClick={() => update({ page: query.page + 1 })}>
            ›
          </button>
        </div>
      </div>
    </>
  );
}
