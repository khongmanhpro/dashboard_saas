import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useStaffDetail, type PeriodType, type ScorePart, type StaffDetail } from "../../api/staff";
import type { Me } from "../../api/types";
import { usePublicConfig } from "../../auth/useAuth";
import { errorMessage, format, t } from "../../i18n";
import { displayName, formatDateTime, formatDuration, initials } from "../../leads/format";
import { formatCompactVnd, formatPercent, formatScore, trendPoints } from "../../staff/format";
import { PeriodSwitch, TierBadge } from "./StaffPage";

function rawText(part: ScorePart): string {
  const r = part.raw;
  const rate = r.rate ?? null;
  const none = t.staffDetail.raw.none;
  switch (part.key) {
    case "close_rate":
      return r.rate === null ? none : format(t.staffDetail.raw.close_rate, { rate: formatPercent(rate), won: String(r.won) });
    case "response_speed":
      return r.median_seconds === null
        ? none
        : format(t.staffDetail.raw.response_speed, { time: formatDuration(Number(r.median_seconds)) });
    case "revenue":
      return r.revenue_vnd === null ? none : format(t.staffDetail.raw.revenue, { value: formatCompactVnd(Number(r.revenue_vnd)) });
    case "phone_rate":
      return r.rate === null ? none : format(t.staffDetail.raw.phone_rate, { rate: formatPercent(rate) });
    case "page_care":
      return t.staffDetail.raw.page_care;
    case "on_time":
      return r.rate === null ? none : format(t.staffDetail.raw.on_time, { rate: formatPercent(rate) });
  }
}

function Parts({ data, canFormula }: { data: StaffDetail; canFormula: boolean }) {
  return (
    <section className="card" aria-labelledby="parts-title">
      <div className="section-head section-head--row">
        <h2 id="parts-title">
          {data.total === null
            ? t.staffDetail.partsTitleNoScore
            : format(t.staffDetail.partsTitle, { n: formatScore(data.total) })}
        </h2>
        {canFormula ? <Link to="/settings#score">{t.staffDetail.formulaLink}</Link> : null}
      </div>
      {data.insufficient_data ? (
        <p className="note">{format(t.staffDetail.insufficient, { min: data.min_leads, n: data.lead_count })}</p>
      ) : null}
      <div className="parts">
        {data.parts.map((part) => {
          const weight =
            part.effective_weight !== null && Number(part.effective_weight) !== part.weight
              ? format(t.staffDetail.weightAdjusted, { w: part.weight, e: formatScore(part.effective_weight) })
              : format(t.staffDetail.weight, { w: part.weight });
          return (
            <div key={part.key} className="part" data-testid={`part-${part.key}`}>
              <span className="part__text">
                <b>{t.staffDetail.parts[part.key]}</b>
                <span>
                  {rawText(part)} · {weight}
                </span>
              </span>
              <span className="part__bar" aria-hidden="true">
                <span style={{ width: `${part.score === null ? 0 : Number(part.score)}%` }} />
              </span>
              <span className="part__points">{formatScore(part.points)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Funnel({ data }: { data: StaffDetail }) {
  const total = data.funnel[0]?.value ?? 0;
  return (
    <section className="card" aria-labelledby="funnel-title">
      <div className="section-head section-head--row">
        <h2 id="funnel-title">{t.staffDetail.funnelTitle}</h2>
        <span>{t.staffDetail.funnelHint}</span>
      </div>
      <div className="funnel">
        {data.funnel.map((step) => {
          const width = total ? (step.value / total) * 100 : 0;
          const avg = step.company_rate === null ? 100 : Number(step.company_rate) * 100;
          const rate =
            step.rate === null
              ? ""
              : step.key === "called"
                ? format(t.staffDetail.calledOfPhone, { rate: formatPercent(step.rate) })
                : formatPercent(step.rate);
          return (
            <div key={step.key} className="funnel__row">
              <span>{t.staffDetail.funnel[step.key]}</span>
              <span className="funnel__track">
                <span className="funnel__fill" style={{ width: `${width}%` }} />
                {step.key !== "leads" && step.key !== "called" ? (
                  <span className="funnel__avg" style={{ left: `${avg}%` }} title={t.staffDetail.companyAvg} />
                ) : null}
              </span>
              <span>
                <b>{step.value}</b> <span className="muted">{rate}</span>
              </span>
            </div>
          );
        })}
      </div>
      <div className="legend note">
        <span>
          <span className="dot dot--fill" aria-hidden="true" />
          {data.member.name}
        </span>
        <span>
          <span className="dot dot--avg" aria-hidden="true" />
          {t.staffDetail.companyAvg}
        </span>
        <span>{t.staffDetail.calledNote}</span>
      </div>
    </section>
  );
}

function Hours({ data }: { data: StaffDetail }) {
  const values = data.hours.map((h) => (h.median_minutes === null ? null : Number(h.median_minutes)));
  const max = Math.max(data.slow_reply_minutes * 2, ...values.map((v) => v ?? 0));
  return (
    <section className="card" aria-labelledby="hours-title">
      <div className="section-head section-head--row">
        <h2 id="hours-title">{t.staffDetail.hoursTitle}</h2>
        <span>{format(t.staffDetail.hoursHint, { m: data.slow_reply_minutes })}</span>
      </div>
      <div className="hours">
        <span className="hours__threshold" style={{ bottom: `${(data.slow_reply_minutes / max) * 100}%` }} aria-hidden="true" />
        {data.hours.map((h, i) => {
          const v = values[i] ?? null;
          return (
            <div key={h.label} className="hours__col">
              <span className="hours__value">{v === null ? t.staff.hidden : formatScore(String(v))}</span>
              <span
                className={v !== null && v > data.slow_reply_minutes ? "hours__bar hours__bar--slow" : "hours__bar"}
                style={{ height: `${v === null ? 0 : (v / max) * 100}%` }}
              />
              <span className="hours__label">{h.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Trend({ data }: { data: StaffDetail }) {
  const totals = data.trend.map((p) => (p.total === null ? null : Number(p.total)));
  const points = trendPoints(totals, 520, 150);
  return (
    <section className="card" aria-labelledby="trend-title">
      <div className="section-head section-head--row">
        <h2 id="trend-title">{format(t.staffDetail.trendTitle, { n: data.trend.length || 8 })}</h2>
      </div>
      {data.trend.length === 0 ? (
        <p className="note">{t.staffDetail.trendEmpty}</p>
      ) : (
        <>
          <svg className="trend" viewBox="-6 -6 532 162" role="img" aria-label={totals.map((v) => v ?? "–").join(", ")}>
            {[0, 50, 100].map((y) => (
              <line key={y} x1="0" x2="520" y1={150 - y * 1.5} y2={150 - y * 1.5} className="trend__grid" />
            ))}
            <polyline points={points} className="trend__line" />
          </svg>
          <div className="trend__labels">
            {data.trend.map((p, i) => (
              <span key={p.first_day}>{format(t.staffDetail.weekShort, { n: i + 1 })}</span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function Recent({ data, timeZone }: { data: StaffDetail; timeZone: string }) {
  return (
    <section className="card" aria-labelledby="recent-title">
      <div className="section-head section-head--row">
        <h2 id="recent-title">{t.staffDetail.recentTitle}</h2>
        <Link to="/leads">{t.staffDetail.allLeads}</Link>
      </div>
      <div className="table-wrap table-wrap--plain">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.staffDetail.recent.lead}</th>
              <th scope="col">{t.staffDetail.recent.at}</th>
              <th scope="col">{t.staffDetail.recent.wait}</th>
              <th scope="col">{t.staffDetail.recent.result}</th>
            </tr>
          </thead>
          <tbody>
            {data.recent.map((lead) => (
              <tr key={lead.id}>
                <td>
                  <Link to={`/leads/${lead.id}`}>{displayName(lead)}</Link>
                </td>
                <td>{formatDateTime(lead.first_inbound_at, timeZone)}</td>
                <td>
                  {lead.response_business_seconds === null
                    ? t.staffDetail.notReplied
                    : formatDuration(lead.response_business_seconds)}
                </td>
                <td>
                  {lead.overdue ? (
                    <span className="pill pill--new">{t.staffDetail.overdue}</span>
                  ) : (
                    <span className={`pill pill--${lead.status}`}>{t.leads.status[lead.status]}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function StaffDetailPage() {
  const { id = "" } = useParams();
  const me = useOutletContext<Me>();
  const [period, setPeriod] = useState<PeriodType>("week");
  const detail = useStaffDetail(id, period);
  const config = usePublicConfig();
  const canFormula = "settings.manage" in me.permissions || "team.manage" in me.permissions;

  if (detail.isLoading) return <div className="muted">{t.app.loading}</div>;
  if (detail.error || !detail.data) {
    const code = detail.error instanceof ApiError ? detail.error.code : "unknown";
    return (
      <>
        <Link to="/staff">{t.staffDetail.back}</Link>
        <div className="card" role="alert">
          {errorMessage(code)}
        </div>
      </>
    );
  }
  const data = detail.data;
  const sub = [
    data.team?.name ?? t.staff.noTeam,
    data.team_lead ? format(t.staffDetail.teamLead, { name: data.team_lead }) : null,
    ...data.pages.map((p) =>
      format(t.staffDetail.pageSince, { page: p.name, date: formatDateTime(p.since, me.workspace.timezone).slice(0, 5) }),
    ),
  ]
    .filter(Boolean)
    .join(" · ");
  const delta = data.delta === null ? null : Number(data.delta);

  return (
    <>
      <Link to="/staff">{t.staffDetail.back}</Link>
      <header className="lead-head">
        <div className="lead-head__who">
          <div className="lead-head__avatar" aria-hidden="true">
            {initials(data.member.name)}
          </div>
          <div>
            <div className="lead-head__title">
              <h1>{data.member.name}</h1>
              {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
            </div>
            <div className="lead-head__sub">{sub}</div>
          </div>
        </div>
        <div className="staff-score">
          <TierBadge tier={data.tier} />
          <span>
            <b data-testid="staff-total">
              {data.total === null ? t.staff.insufficient : format(t.staffDetail.points, { n: formatScore(data.total) })}
            </b>
            <span className="muted">
              {delta !== null && delta !== 0
                ? `${format(delta > 0 ? t.staffDetail.up : t.staffDetail.down, { n: formatScore(String(Math.abs(delta))) })} · `
                : ""}
              {data.rank !== null ? format(t.staffDetail.rankOf, { rank: data.rank, total: data.ranked_count }) : ""}
            </span>
          </span>
        </div>
      </header>
      <PeriodSwitch value={period} onChange={setPeriod} />
      <div className="grid-2">
        <Parts data={data} canFormula={canFormula} />
        <Funnel data={data} />
      </div>
      <div className="grid-2">
        <Hours data={data} />
        <Trend data={data} />
      </div>
      <Recent data={data} timeZone={me.workspace.timezone} />
    </>
  );
}
