import { useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  PERIOD_TYPES,
  TIERS,
  useFormula,
  useLeaderboard,
  useRecompute,
  type LeaderboardRow,
  type PeriodType,
  type Tier,
} from "../../api/staff";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime, formatDuration, initials } from "../../leads/format";
import { formatCompactVnd, formatDelta, formatPercent, formatScore, tierRanges } from "../../staff/format";
import { AddMemberDialog } from "./AddMemberDialog";
import { ImportDialog } from "./ImportDialog";

export function TierBadge({ tier }: { tier: Tier | null }) {
  if (!tier) return null;
  return <span className={`tier tier--${tier}`}>{tier}</span>;
}

export function PeriodSwitch({ value, onChange }: { value: PeriodType; onChange: (p: PeriodType) => void }) {
  return (
    <div className="segmented" role="group" aria-label={t.staff.periodLabel}>
      {PERIOD_TYPES.map((p) => (
        <button key={p} type="button" aria-pressed={value === p} onClick={() => onChange(p)}>
          {t.staff.periods[p]}
        </button>
      ))}
    </div>
  );
}

function ScoreCell({ row }: { row: LeaderboardRow }) {
  if (row.insufficient_data) return <span className="muted">{t.staff.insufficient}</span>;
  const delta = formatDelta(row.delta);
  return (
    <span className="score-cell">
      <TierBadge tier={row.tier} />
      <b>{formatScore(row.total)}</b>
      {row.total !== null ? (
        <span className="score-bar" aria-hidden="true">
          <span style={{ width: `${Number(row.total)}%` }} />
        </span>
      ) : null}
      {delta ? <span className={`delta delta--${delta.dir}`}>{delta.text}</span> : null}
    </span>
  );
}

export function StaffPage() {
  const me = useOutletContext<Me>();
  const timeZone = me.workspace.timezone;
  const [period, setPeriod] = useState<PeriodType>("week");
  const [search, setSearch] = useState("");
  const [teamId, setTeamId] = useState("");
  const [tier, setTier] = useState<Tier | "">("");
  const board = useLeaderboard(period);
  const formula = useFormula();
  const recompute = useRecompute();
  const canSettings = "settings.manage" in me.permissions || "team.manage" in me.permissions;
  const canRecompute = "score_formula.edit" in me.permissions;
  const canManage = "member.manage" in me.permissions;
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState<"import" | "add" | null>(params.get("import") ? "import" : null);
  const closeDialog = () => {
    setDialog(null);
    if (params.get("import")) setParams({}, { replace: true });
  };

  const data = board.data;
  const q = search.trim().toLowerCase();
  const rows = (data?.rows ?? []).filter(
    (r) =>
      (!q || r.member.name.toLowerCase().includes(q) || r.pages.some((p) => p.toLowerCase().includes(q))) &&
      (!teamId || r.team?.id === teamId) &&
      (!tier || r.tier === tier),
  );
  const ranked = data?.tiers ? TIERS.reduce((sum, x) => sum + (data.tiers?.[x] ?? 0), 0) : 0;
  const ranges = formula.data ? tierRanges(formula.data) : null;

  let sub = "";
  if (data?.period.first_day && data.period.last_day) {
    const [, fm, fd] = data.period.first_day.split("-");
    const [, lm, ld] = data.period.last_day.split("-");
    sub = format(t.staff.subtitle, {
      n: data.rows.filter((r) => !r.insufficient_data).length,
      period: format(t.staff.periodRange, { from: `${fd}/${fm}`, to: `${ld}/${lm}` }),
    });
    if (data.period.computed_at) {
      sub += ` · ${format(t.staff.computedAt, { time: formatDateTime(data.period.computed_at, timeZone) })}`;
    }
  }

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.staff.title} />
          <div className="page-sub">
            {sub || t.staff.notComputed}
            {data?.period.is_final ? <span className="tag tag--good">{t.staff.finalBadge}</span> : null}
          </div>
        </div>
        <div className="row-actions">
          {canManage ? (
            <>
              <button type="button" className="btn" onClick={() => setDialog("import")}>
                {t.imports.open}
              </button>
              <button type="button" className="btn" onClick={() => setDialog("add")}>
                {t.addMember.open}
              </button>
            </>
          ) : null}
          {canRecompute ? (
            <button type="button" className="btn" disabled={recompute.isPending} onClick={() => recompute.mutate()}>
              {recompute.isPending ? t.staff.recomputing : t.staff.recompute}
            </button>
          ) : null}
        </div>
      </div>
      {dialog === "import" && canManage ? <ImportDialog onClose={closeDialog} /> : null}
      {dialog === "add" && canManage ? <AddMemberDialog me={me} onClose={closeDialog} /> : null}
      {recompute.error instanceof ApiError ? (
        <div className="alert alert--error" role="alert">
          {errorMessage(recompute.error.code)}
        </div>
      ) : null}

      {data?.tiers && ranges ? (
        <section className="card" aria-label={format(t.staff.tiersTitle, { n: ranked })}>
          <div className="section-head section-head--row">
            <h2>{format(t.staff.tiersTitle, { n: ranked })}</h2>
            <span>
              {format(t.staff.insufficientNote, { n: data.insufficient_count ?? 0, min: data.min_leads })}
            </span>
          </div>
          <div className="tier-bar" role="img" aria-label={TIERS.map((x) => `${x} ${data.tiers?.[x]}`).join(", ")}>
            {TIERS.map((x) => (
              <span key={x} className={`tier-bar__seg tier-bg--${x}`} style={{ flex: data.tiers?.[x] ?? 0 }} />
            ))}
          </div>
          <div className="tier-legend">
            {TIERS.map((x) => (
              <button
                key={x}
                type="button"
                aria-pressed={tier === x}
                onClick={() => setTier(tier === x ? "" : x)}
              >
                <span className={`dot tier-bg--${x}`} aria-hidden="true" />
                <b>{x}</b>
                <span className="muted">{ranges[x]}</span>
                <span>{format(t.staff.people, { n: data.tiers?.[x] ?? 0 })}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {data?.kpis ? (
        <section className="kpis" aria-label={t.staff.title}>
          {[
            [t.staff.kpis.leads, String(data.kpis.lead_count)],
            [
              t.staff.kpis.reply,
              data.kpis.median_response_seconds === null ? t.staff.hidden : formatDuration(data.kpis.median_response_seconds),
            ],
            [t.staff.kpis.phone, formatPercent(data.kpis.phone_rate)],
            [t.staff.kpis.close, formatPercent(data.kpis.close_rate)],
            [t.staff.kpis.revenue, formatCompactVnd(data.kpis.revenue_vnd)],
            [t.staff.kpis.overdue, String(data.kpis.overdue_count)],
          ].map(([label, value]) => (
            <div key={label} className="kpi">
              <div className="kpi__label">{label}</div>
              <div className="kpi__value">{value}</div>
            </div>
          ))}
        </section>
      ) : null}

      <div className="filters">
        <label className="filters__search">
          <span className="sr-only">{t.staff.search}</span>
          <input
            type="search"
            value={search}
            placeholder={t.staff.searchPlaceholder}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {data && data.teams.length > 1 ? (
          <label className="select">
            {t.staff.team}
            <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">{t.staff.allTeams}</option>
              {data.teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="select">
          {t.staff.tier}
          <select value={tier} onChange={(e) => setTier(e.target.value as Tier | "")}>
            <option value="">{t.staff.allTiers}</option>
            {TIERS.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <PeriodSwitch value={period} onChange={setPeriod} />
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{t.staff.table.rank}</th>
              <th scope="col">{t.staff.table.member}</th>
              <th scope="col">{t.staff.table.pages}</th>
              <th scope="col">{t.staff.table.score}</th>
              <th scope="col">{t.staff.table.leads}</th>
              <th scope="col">{t.staff.table.reply}</th>
              <th scope="col">{t.staff.table.phone}</th>
              <th scope="col">{t.staff.table.close}</th>
              <th scope="col">{t.staff.table.revenue}</th>
              <th scope="col">{t.staff.table.overdue}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const visible = row.total !== null || row.lead_count !== null;
              return (
                <tr key={row.member.id} className={row.is_self ? "row--self" : undefined} data-testid="staff-row">
                  <td>{row.rank ?? t.staff.hidden}</td>
                  <td>
                    {visible ? (
                      <Link to={`/staff/${row.member.id}`} className="member-link">
                        <span className="avatar" aria-hidden="true">
                          {initials(row.member.name)}
                        </span>
                        <span>
                          <span className="member-link__name">
                            {row.member.name}
                            {row.is_self ? <span className="tag tag--info">{t.staff.you}</span> : null}
                          </span>
                          <span className="member-link__team">{row.team?.name ?? t.staff.noTeam}</span>
                        </span>
                      </Link>
                    ) : (
                      <span className="member-link">
                        <span className="avatar" aria-hidden="true">
                          {initials(row.member.name)}
                        </span>
                        <span className="member-link__name">{row.member.name}</span>
                      </span>
                    )}
                  </td>
                  <td>{row.pages.join(", ") || <span className="muted">{t.staff.noPage}</span>}</td>
                  <td>
                    {visible ? <ScoreCell row={row} /> : <TierBadge tier={row.tier} />}
                  </td>
                  <td>{row.lead_count ?? t.staff.hidden}</td>
                  <td>
                    {row.median_response_seconds === null ? t.staff.hidden : formatDuration(row.median_response_seconds)}
                  </td>
                  <td>{formatPercent(row.phone_rate)}</td>
                  <td>{formatPercent(row.close_rate)}</td>
                  <td>{formatCompactVnd(row.revenue_vnd)}</td>
                  <td className={row.overdue_count ? "timer--hot" : undefined}>{row.overdue_count ?? t.staff.hidden}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!board.isLoading && rows.length === 0 ? (
          <div className="card muted">{data?.rows.length ? t.staff.empty : t.staff.notComputed}</div>
        ) : null}
      </div>
      <div className="table-foot">
        <span>{format(t.staff.footer, { n: rows.length })}</span>
        {canSettings ? <Link to="/settings#score">{t.staff.howScored}</Link> : null}
      </div>
    </>
  );
}
