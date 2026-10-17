import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { usePageDetail, type PageDetail, type PageStatus } from "../../api/reports";
import type { Me } from "../../api/types";
import { usePublicConfig } from "../../auth/useAuth";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime } from "../../leads/format";
import { formatCount, formatNumber, formatRate, heatLevel, linePoints, shortDate } from "../../reports/format";
import { KpiCard, StatusPill } from "./common";

type Tab = "overview" | "posts" | "audience" | "schedule";
const TABS: Tab[] = ["overview", "posts", "audience", "schedule"];
const LATER: Tab[] = ["audience", "schedule"];
const STATUS_TONE: Record<PageStatus, "good" | "bad" | "warn"> = { ok: "good", declining: "bad", disconnected: "warn" };
const POST_TYPES = ["photo", "video", "reel", "link", "status"] as const;

function Kpis({ data }: { data: PageDetail }) {
  const k = data.kpis;
  const posts = k.posts.value === null ? null : Number(k.posts.value);
  return (
    <section aria-label={t.pageDetail.kpisLabel} className="kpis kpis--wide">
      <KpiCard
        label={t.pageDetail.kpis.followers}
        value={formatNumber(k.followers)}
        note={k.new_follows.value !== null ? format(t.pageDetail.newFollows, { n: formatNumber(k.new_follows.value) }) : undefined}
      />
      <KpiCard label={t.pageDetail.kpis.views} value={formatCount(k.views.value === null ? null : Number(k.views.value))} metric={k.views} kind="percent" better="up" />
      <KpiCard label={t.pageDetail.kpis.reach} value={formatNumber(k.reach.value)} metric={k.reach} kind="percent" better="up" />
      <KpiCard label={t.pageDetail.kpis.engagements} value={formatNumber(k.engagements.value)} metric={k.engagements} kind="percent" better="up" />
      <KpiCard label={t.pageDetail.kpis.video_views} value={formatNumber(k.video_views.value)} metric={k.video_views} kind="percent" better="up" />
      <KpiCard
        label={t.pageDetail.kpis.posts}
        value={formatNumber(posts)}
        note={posts !== null ? format(t.pageDetail.perDay, { n: String(Math.round((posts / 30) * 10) / 10).replace(".", ",") }) : undefined}
      />
    </section>
  );
}

function ViewsChart({ data }: { data: PageDetail }) {
  const values = data.daily_views.map((d) => d.value);
  const points = linePoints(values, 600, 200, 8);
  const ticks = [0, 7, 14, 21, data.daily_views.length - 1].map((i) => data.daily_views[i]).filter(Boolean);
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{t.pageDetail.viewsTitle}</h2>
        <span>{t.pageDetail.days30}</span>
      </div>
      <svg className="line-chart" viewBox="0 0 600 200" role="img" aria-label={t.pageDetail.viewsAria} preserveAspectRatio="none">
        <line x1="0" y1="192" x2="600" y2="192" stroke="currentColor" strokeOpacity="0.2" />
        {points ? (
          <>
            <polyline className="area" points={`8,192 ${points} 592,192`} />
            <polyline className="line" points={points} />
          </>
        ) : null}
      </svg>
      <div className="axis-labels" aria-hidden="true">
        {ticks.map((d) => (
          <span key={d!.day}>{shortDate(d!.day)}</span>
        ))}
      </div>
    </div>
  );
}

function Heatmap({ data }: { data: PageDetail }) {
  const grid = data.heatmap;
  const max = grid ? Math.max(0, ...grid.flat().map((v) => (v === null ? 0 : Number(v)))) : 0;
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{t.pageDetail.heatTitle}</h2>
        <span>{t.pageDetail.heatHint}</span>
      </div>
      {grid ? (
        <>
          <div className="heatmap" role="img" aria-label={t.pageDetail.heatAria} data-testid="heatmap">
            <span />
            {t.pageDetail.slots.map((s) => (
              <span key={s}>{s}</span>
            ))}
            {grid.map((row, d) => (
              <HeatRow key={d} day={t.pageDetail.weekdays[d] ?? ""} row={row} max={max} />
            ))}
          </div>
          <div className="heat-legend" aria-hidden="true">
            <span>{t.pageDetail.heatLow}</span>
            <i />
            <span>{t.pageDetail.heatHigh}</span>
          </div>
        </>
      ) : (
        <p className="muted">{format(t.pageDetail.heatEmpty, { n: data.heatmap_min_posts })}</p>
      )}
    </div>
  );
}

function HeatRow({ day, row, max }: { day: string; row: (string | null)[]; max: number }) {
  return (
    <>
      <span>{day}</span>
      {row.map((v, i) => (
        <span key={i} className={`heat heat--${heatLevel(v, max)}`} title={v === null ? "" : formatRate(v)} />
      ))}
    </>
  );
}

function Posts({ data, timeZone }: { data: PageDetail; timeZone: string }) {
  const [type, setType] = useState("");
  const rows = data.posts.filter((p) => !type || p.type === type);
  return (
    <section className="card card--tight" style={{ padding: 0 }}>
      <div className="card__head" style={{ padding: "16px 18px 0" }}>
        <h2>{t.pageDetail.postsTitle}</h2>
        <label className="report-select">
          {t.pageDetail.type}
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">{t.pageDetail.allTypes}</option>
            {POST_TYPES.map((p) => (
              <option key={p} value={p}>
                {t.pageDetail.types[p]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-wrap table-wrap--plain">
        <table data-testid="posts-table">
          <thead>
            <tr>
              <th scope="col">{t.pageDetail.postCols.post}</th>
              <th scope="col">{t.pageDetail.postCols.type}</th>
              <th scope="col" className="num">{t.pageDetail.postCols.views}</th>
              <th scope="col" className="num">{t.pageDetail.postCols.reactions}</th>
              <th scope="col" className="num">{t.pageDetail.postCols.comments}</th>
              <th scope="col" className="num">{t.pageDetail.postCols.shares}</th>
              <th scope="col" className="num">{t.pageDetail.postCols.rate}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td>
                  <span className="post-cell">
                    {p.permalink ? (
                      <a href={p.permalink} target="_blank" rel="noopener noreferrer">
                        <b>{p.excerpt ?? t.pageDetail.noExcerpt}</b>
                      </a>
                    ) : (
                      <b>{p.excerpt ?? t.pageDetail.noExcerpt}</b>
                    )}
                    <span>{formatDateTime(p.created_time, timeZone)}</span>
                  </span>
                </td>
                <td>{t.pageDetail.types[p.type as (typeof POST_TYPES)[number]] ?? p.type}</td>
                <td className="num">{formatNumber(p.views)}</td>
                <td className="num">{formatNumber(p.reactions)}</td>
                <td className="num">{formatNumber(p.comments)}</td>
                <td className="num">{formatNumber(p.shares)}</td>
                <td className="num">
                  <b>{formatRate(p.engagement_rate)}</b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? <p className="muted" style={{ padding: 16 }}>{t.pageDetail.postsEmpty}</p> : null}
      </div>
    </section>
  );
}

export function PageDetailPage() {
  const { id = "" } = useParams();
  const me = useOutletContext<Me>();
  const timeZone = me.workspace.timezone;
  const config = usePublicConfig();
  const detail = usePageDetail(id);
  const [tab, setTab] = useState<Tab>("overview");
  const data = detail.data;

  if (detail.error instanceof ApiError) {
    return (
      <>
        <Link to="/pages" className="breadcrumb">
          {t.pageDetail.back}
        </Link>
        <div className="card">{errorMessage(detail.error.code)}</div>
      </>
    );
  }
  if (!data) return <div className="card muted">{t.reports.loading}</div>;

  return (
    <>
      <Link to="/pages" className="breadcrumb">
        {t.pageDetail.back}
      </Link>
      <header className="card page-hero">
        <div className="page-hero__who">
          <div className="page-hero__avatar" aria-hidden="true">
            {data.name.replace("[", "").slice(0, 1).toUpperCase()}
          </div>
          <div>
            <div className="page-hero__title">
              <h1>{data.name}</h1>
              <StatusPill tone={STATUS_TONE[data.status]}>{t.pageDetail.status[data.status]}</StatusPill>
              {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
            </div>
            <div className="page-sub">
              {format(t.pageDetail.meta, {
                team: data.team ? `${data.team} · ` : "",
                owner: data.owner?.name ?? t.pages.noOwner,
                id: data.fb_page_id,
              })}
              {data.content_synced_at ? ` · ${format(t.pageDetail.syncedAt, { time: formatDateTime(data.content_synced_at, timeZone) })}` : ""}
            </div>
          </div>
        </div>
        <a className="btn btn--link" href={`https://www.facebook.com/${data.fb_page_id}`} target="_blank" rel="noopener noreferrer">
          {t.pageDetail.openFacebook}
        </a>
      </header>

      <div className="tabs-line" role="tablist" aria-label={t.pageDetail.tabsLabel}>
        {TABS.map((key) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
            {t.pageDetail.tabs[key]}
            {LATER.includes(key) ? <span className="nav-tag">{t.pageDetail.later}</span> : null}
          </button>
        ))}
      </div>

      {!data.content_synced_at ? <div className="notice notice--info">{t.pageDetail.notSynced}</div> : null}

      {tab === "overview" ? (
        <>
          <Kpis data={data} />
          <section className="report-grid">
            <ViewsChart data={data} />
            <Heatmap data={data} />
          </section>
          <Posts data={data} timeZone={timeZone} />
        </>
      ) : null}
      {tab === "posts" ? <Posts data={data} timeZone={timeZone} /> : null}
      {LATER.includes(tab) ? <div className="card muted">{t.pageDetail.laterBody}</div> : null}
    </>
  );
}
