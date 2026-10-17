import { useState } from "react";
import { Link } from "react-router-dom";

import {
  overviewExportUrl,
  useOverview,
  type BoardRow,
  type Overview,
  type RangeKey,
  type RangeParams,
} from "../../api/reports";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDuration, initials } from "../../leads/format";
import {
  formatMoney,
  formatMoneyShort,
  formatNumber,
  formatRate,
  formatSeconds,
  linePoints,
  noteText,
  shortDate,
  weekdayShort,
} from "../../reports/format";
import { formatPercent, formatScore } from "../../staff/format";
import { TierBadge } from "../staff/StaffPage";
import { KpiCard, MissingFx, RangePicker } from "./common";
import { ApiError } from "../../api/client";

const RANGE_KEYS: RangeKey[] = ["today", "7d", "30d", "custom"];

/** Khoảng của Tổng quan → bộ lọc kỳ của màn Khách hàng. */
function leadsPeriod(range: RangeKey): string {
  return range === "today" || range === "7d" || range === "30d" ? range : "all";
}

function ratio(part: number, whole: number): string {
  return whole > 0 ? formatPercent(part / whole) : formatRate(null);
}

type Tone = "bad" | "warn" | "info" | "ok";

interface AlertItem {
  key: string;
  num: number;
  title: string;
  desc: string;
  href: string;
  tone: Tone;
  mobile: string;
}

function alertItems(data: Overview): AlertItem[] {
  const a = data.alerts;
  const items: AlertItem[] = [
    {
      key: "overdue",
      num: a.overdue,
      title: a.overdue ? t.overview.alerts.overdue : t.overview.alerts.overdueNone,
      desc: a.overdue
        ? format(t.overview.alerts.overdueDesc, {
            pages: a.overdue_pages,
            age: formatDuration((a.overdue_oldest_hours ?? 0) * 3600),
          })
        : "",
      href: "/leads?chip=overdue&period=all",
      tone: a.overdue ? "bad" : "ok",
      mobile: format(t.overview.mobileAlerts.overdue, { n: a.overdue }),
    },
    {
      key: "slow",
      num: a.slow_staff,
      title: t.overview.alerts.slow,
      desc: format(t.overview.alerts.slowDesc, { m: a.slow_reply_minutes }),
      href: "/staff",
      tone: a.slow_staff ? "warn" : "ok",
      mobile: format(t.overview.mobileAlerts.slow, { n: a.slow_staff }),
    },
  ];
  if (a.unassigned_pages !== null) {
    items.push({
      key: "unassigned",
      num: a.unassigned_pages,
      title: t.overview.alerts.unassigned,
      desc: t.overview.alerts.unassignedDesc,
      href: "/pages?tab=unassigned",
      tone: a.unassigned_pages ? "info" : "ok",
      mobile: format(t.overview.mobileAlerts.unassigned, { n: a.unassigned_pages }),
    });
  }
  if (a.bm_disconnected !== null) {
    items.push({
      key: "bm",
      num: a.bm_disconnected,
      title: a.bm_disconnected ? t.overview.alerts.bm : t.overview.alerts.bmNone,
      desc: a.bm_disconnected
        ? format(t.overview.alerts.bmDesc, { name: a.bm_disconnected_name ?? "", pages: a.bm_disconnected_pages })
        : "",
      href: "/bm",
      tone: a.bm_disconnected ? "bad" : "ok",
      mobile: "",
    });
  }
  if (a.expensive_campaigns !== null) {
    items.push({
      key: "expensive",
      num: a.expensive_campaigns,
      title: t.overview.alerts.expensive,
      desc: t.overview.alerts.expensiveDesc,
      href: "/ads",
      tone: a.expensive_campaigns ? "warn" : "ok",
      mobile: format(t.overview.mobileAlerts.expensive, { n: a.expensive_campaigns }),
    });
  }
  return items;
}

function Alerts({ data }: { data: Overview }) {
  const items = alertItems(data).filter((i) => i.key !== "expensive");
  return (
    <section aria-label={t.overview.alertsLabel} className="alert-cards only-desktop" data-testid="overview-alerts">
      {items.map((item) => (
        <Link key={item.key} to={item.href} className={`alert-card alert-card--${item.tone}`} data-testid={`alert-${item.key}`}>
          <span className="alert-card__num">{item.num}</span>
          <span className="alert-card__text">
            <span className="alert-card__title">{item.title}</span>
            {item.desc ? <span className="alert-card__desc">{item.desc}</span> : null}
          </span>
        </Link>
      ))}
    </section>
  );
}

function Kpis({ data, mobile }: { data: Overview; mobile: boolean }) {
  const k = data.kpis;
  const cards = [
    <KpiCard key="new" label={t.overview.kpis.new_leads} value={formatNumber(k.new_leads.value)} metric={k.new_leads} kind="percent" better="up" />,
    ...(mobile
      ? []
      : [
          <KpiCard
            key="speed"
            label={t.overview.kpis.median_response_seconds}
            value={formatSeconds(k.median_response_seconds.value)}
            metric={k.median_response_seconds}
            kind="minutes"
            better="down"
          />,
          <KpiCard key="phone" label={t.overview.kpis.phone_rate} value={formatRate(k.phone_rate.value)} metric={k.phone_rate} kind="points" better="up" />,
        ]),
    <KpiCard key="close" label={t.overview.kpis.close_rate} value={formatRate(k.close_rate.value)} metric={k.close_rate} kind="points" better="up" />,
    <KpiCard key="revenue" label={t.overview.kpis.revenue_vnd} value={formatMoneyShort(k.revenue_vnd.value)} metric={k.revenue_vnd} kind="percent" better="up" />,
  ];
  if (k.cost_per_won_vnd) {
    cards.push(
      <KpiCard
        key="cpw"
        label={t.overview.kpis.cost_per_won_vnd}
        value={formatMoney(k.cost_per_won_vnd.value)}
        metric={k.cost_per_won_vnd}
        kind="percent"
        better="down"
        hint={t.overview.costHint}
      />,
    );
  }
  return (
    <section aria-label={t.overview.kpisLabel} className={mobile ? "kpis kpis--mobile only-mobile" : "kpis kpis--wide only-desktop"} data-testid={mobile ? undefined : "overview-kpis"}>
      {cards}
    </section>
  );
}

function FunnelSection({ data, range }: { data: Overview; range: RangeKey }) {
  const f = data.funnel;
  const period = leadsPeriod(range);
  const steps = [
    { key: "new", value: f.new, rate: t.overview.funnelRate.new, loss: null },
    {
      key: "replied",
      value: f.replied,
      rate: format(t.overview.funnelRate.replied, { rate: ratio(f.replied, f.new) }),
      loss: f.unreplied
        ? { text: format(t.overview.funnelLoss.unreplied, { n: f.unreplied }), href: `/leads?chip=unreplied&period=${period}`, tone: "bad" }
        : null,
    },
    {
      key: "phone",
      value: f.phone,
      rate: format(t.overview.funnelRate.phone, { rate: ratio(f.phone, f.replied) }),
      loss: f.replied_no_phone
        ? { text: format(t.overview.funnelLoss.noPhone, { n: f.replied_no_phone }), href: `/leads?period=${period}`, tone: "muted" }
        : null,
    },
    {
      key: "called",
      value: f.called,
      rate: format(t.overview.funnelRate.called, { rate: ratio(f.called, f.phone) }),
      loss: f.phone_not_called
        ? {
            text: format(t.overview.funnelLoss.notCalled, { n: f.phone_not_called }),
            href: `/leads?chip=phone_not_called&period=${period}`,
            tone: "warn",
          }
        : null,
    },
    {
      key: "won",
      value: f.won,
      rate: format(t.overview.funnelRate.won, { rate: ratio(f.won, f.called), rateNew: ratio(f.won, f.new) }),
      loss:
        f.lost || f.callback
          ? { text: format(t.overview.funnelLoss.lost, { lost: f.lost, callback: f.callback }), href: `/leads?period=${period}`, tone: "muted" }
          : null,
    },
  ] as const;
  return (
    <section className="card card--tight only-desktop" aria-labelledby="funnel-title" data-testid="overview-funnel">
      <div className="card__head">
        <h2 id="funnel-title">{t.overview.funnelTitle}</h2>
        <span>{t.overview.funnelHint}</span>
      </div>
      <div className="funnel">
        {steps.map((s) => (
          <div className="funnel__step" key={s.key}>
            <span className="funnel__label">{t.overview.funnel[s.key]}</span>
            <span className="funnel__value">{formatNumber(s.value)}</span>
            <div className="funnel__track">
              <div className="funnel__bar" style={{ width: `${Math.max(4, f.new ? Math.round((s.value / f.new) * 100) : 0)}%` }} />
            </div>
            <span className="funnel__rate">{s.rate}</span>
            {s.loss ? (
              <Link to={s.loss.href} className={`funnel__loss funnel__loss--${s.loss.tone}`}>
                {s.loss.text}
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function DailyChart({ data }: { data: Overview }) {
  const max = Math.max(1, ...data.daily.map((d) => d.new));
  const many = data.daily.length > 10;
  const every = Math.ceil(data.daily.length / 8);
  const totals = data.daily.reduce((a, d) => ({ new: a.new + d.new, won: a.won + d.won }), { new: 0, won: 0 });
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{t.overview.dailyTitle}</h2>
        <span className="legend">
          <span>
            <i className="legend__new" aria-hidden="true" />
            {t.overview.dailyNew}
          </span>
          <span>
            <i className="legend__won" aria-hidden="true" />
            {t.overview.dailyWon}
          </span>
        </span>
      </div>
      <div className="bars" role="img" aria-label={format(t.overview.dailyAria, totals)}>
        {data.daily.map((d) => (
          <div className="bars__day" key={d.day} title={`${shortDate(d.day)}: ${d.new} / ${d.won}`}>
            <i className="legend__new" style={{ height: `${Math.round((d.new / max) * 100)}%` }} />
            <i className="legend__won" style={{ height: `${Math.round((d.won / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="bars__labels" aria-hidden="true">
        {data.daily.map((d, i) => (
          <span key={d.day}>{many ? (i % every === 0 ? shortDate(d.day) : "") : weekdayShort(d.day)}</span>
        ))}
      </div>
    </div>
  );
}

function Campaigns({ data }: { data: Overview }) {
  if (!data.campaigns) return null;
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{t.overview.campaignsTitle}</h2>
        <Link to="/ads">{t.overview.campaignsLink}</Link>
      </div>
      {data.campaigns.length === 0 ? (
        <p className="muted">{t.overview.campaignsEmpty}</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="mini-table" data-testid="overview-campaigns">
            <thead>
              <tr>
                <th scope="col">{t.overview.campaignCols.name}</th>
                <th scope="col">{t.overview.campaignCols.spend}</th>
                <th scope="col">{t.overview.campaignCols.leads}</th>
                <th scope="col">{t.overview.campaignCols.won}</th>
                <th scope="col">{t.overview.campaignCols.cpw}</th>
              </tr>
            </thead>
            <tbody>
              {data.campaigns.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{formatMoneyShort(c.spend_vnd)}</td>
                  <td>{formatNumber(c.leads)}</td>
                  <td>{formatNumber(c.won)}</td>
                  <td>
                    <b>{formatMoney(c.cost_per_won_vnd)}</b>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <span className="card__note">{t.overview.campaignsNote}</span>
    </div>
  );
}

function Board({ title, rows, weak }: { title: string; rows: BoardRow[]; weak: boolean }) {
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{title}</h2>
        <Link to="/staff">{t.overview.boardLink}</Link>
      </div>
      {rows.length === 0 ? <p className="muted">{t.overview.boardEmpty}</p> : null}
      <div>
        {rows.map((r) => {
          const note = noteText(r);
          return (
            <Link key={r.member.id} to={`/staff/${r.member.id}`} className="board-row">
              <span className="board-row__rank">{r.rank ?? ""}</span>
              <span className="avatar" aria-hidden="true">
                {initials(r.member.name)}
              </span>
              <span className="board-row__who">
                <span className="board-row__name">{r.member.name}</span>
                <span className={weak ? "board-row__note board-row__note--bad" : "board-row__note"}>
                  {[r.page, note ? (weak ? t.overview.weakPrefix + note : note) : null].filter(Boolean).join(" · ")}
                </span>
              </span>
              <span className="board-row__score">{formatScore(r.total)}</span>
              <TierBadge tier={r.tier} />
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function MobileExtras({ data }: { data: Overview }) {
  const won = data.daily.map((d) => d.won);
  const points = linePoints(won, 330, 110);
  const todo = alertItems(data).filter((i) => i.mobile && i.num > 0);
  return (
    <>
      <div className="card card--tight only-mobile">
        <span className="card__head">
          <h2>{t.overview.mobileWonTitle}</h2>
        </span>
        <svg className="line-chart" viewBox="0 0 330 110" style={{ height: 110 }} role="img" aria-label={t.overview.mobileWonTitle}>
          {points ? (
            <>
              <polyline className="area" points={`2,108 ${points} 328,108`} />
              <polyline className="line" points={points} />
            </>
          ) : null}
        </svg>
      </div>
      {todo.length ? (
        <div className="todo-list only-mobile">
          <h2 className="sr-only">{t.overview.mobileTodo}</h2>
          {todo.map((i) => (
            <Link key={i.key} to={i.href}>
              <span>{i.mobile}</span>
              <span aria-hidden="true">›</span>
            </Link>
          ))}
        </div>
      ) : null}
    </>
  );
}

export function OverviewPage() {
  const [range, setRange] = useState<RangeParams>({ range: "7d" });
  const [teamId, setTeamId] = useState("");
  const overview = useOverview(range, teamId);
  const data = overview.data;
  const error = overview.error instanceof ApiError ? overview.error : null;

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.overview.title} />
          {data ? (
            <div className="page-sub">{format(t.overview.subtitle, { members: data.members, pages: data.pages, bms: data.bms })}</div>
          ) : null}
        </div>
        <div className="row-actions">
          <RangePicker keys={RANGE_KEYS} value={range} onChange={setRange} />
          {data && data.teams.length > 1 ? (
            <label className="report-select only-desktop">
              {t.reports.team}
              <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">{t.reports.allTeams}</option>
                {data.teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <a className="btn btn--primary btn--link only-desktop" href={overviewExportUrl(range, teamId)} download>
            {t.reports.export}
          </a>
        </div>
      </div>
      {error ? <div className="alert alert--error">{errorMessage(error.code, error.detail)}</div> : null}
      {!data ? (
        overview.isLoading ? <div className="card muted">{t.reports.loading}</div> : null
      ) : (
        <>
          <Alerts data={data} />
          <MissingFx currencies={data.missing_fx} />
          <Kpis data={data} mobile={false} />
          <Kpis data={data} mobile />
          <MobileExtras data={data} />
          <FunnelSection data={data} range={range.range} />
          <section className="grid-2 only-desktop">
            <DailyChart data={data} />
            <Campaigns data={data} />
          </section>
          <section className="grid-2 only-desktop">
            <Board title={t.overview.topTitle} rows={data.boards.top} weak={false} />
            <Board title={t.overview.bottomTitle} rows={data.boards.bottom} weak />
          </section>
        </>
      )}
    </>
  );
}
