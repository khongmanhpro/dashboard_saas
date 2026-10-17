import { useState } from "react";

import { ApiError } from "../../api/client";
import {
  ADS_LEVELS,
  useAdsReport,
  useAlertRules,
  useToggleRule,
  type AdsLevel,
  type AdsReport,
  type AdsRow,
  type AlertRule,
  type RangeKey,
  type RangeParams,
  type RuleType,
} from "../../api/reports";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatMoney, formatMoneyShort, formatNumber, formatRate, formatRoas, metricDelta, shortDate } from "../../reports/format";
import { KpiCard, MissingFx, RangePicker, StatusPill } from "./common";

const RANGE_KEYS: RangeKey[] = ["30d", "7d", "month", "custom"];
const ALERT_RULES: RuleType[] = ["cost_per_result", "cost_per_won", "frequency"];

function frequencyText(value: string | null): string {
  return value === null ? "–" : String(Number(value)).replace(".", ",");
}

function Kpis({ data }: { data: AdsReport }) {
  const k = data.kpis;
  const cpr = metricDelta(k.cost_per_result_vnd, "percent", "down");
  return (
    <section aria-label={t.ads.kpisLabel} className="kpis" data-testid="ads-kpis">
      <KpiCard label={t.ads.kpis.spend_vnd} value={formatMoneyShort(k.spend_vnd.value)} metric={k.spend_vnd} kind="percent" better="up" />
      <KpiCard label={t.ads.kpis.results} value={formatNumber(k.results.value)} note={t.ads.resultsNote} />
      <KpiCard
        label={t.ads.kpis.cost_per_result_vnd}
        value={formatMoney(k.cost_per_result_vnd.value)}
        metric={k.cost_per_result_vnd}
        kind="percent"
        better="down"
        hint={cpr ? (cpr.tone === "good" ? t.ads.better : t.ads.worse) : undefined}
      />
      <KpiCard label={t.ads.kpis.ctr} value={formatRate(k.ctr.value)} metric={k.ctr} kind="points" better="up" />
      <KpiCard label={t.ads.kpis.cpm_vnd} value={formatMoney(k.cpm_vnd.value)} metric={k.cpm_vnd} kind="percent" better="down" />
      <KpiCard label={t.ads.kpis.frequency} value={frequencyText(k.frequency.value)} note={t.ads.frequencyNote} />
      <KpiCard label={t.ads.kpis.won} value={formatNumber(k.won.value)} metric={k.won} kind="percent" better="up" />
      <KpiCard
        label={t.ads.kpis.cost_per_won_vnd}
        value={formatMoney(k.cost_per_won_vnd.value)}
        metric={k.cost_per_won_vnd}
        kind="percent"
        better="down"
      />
      <KpiCard
        label={t.ads.kpis.roas}
        value={formatRoas(k.roas.value)}
        metric={k.roas}
        kind="percent"
        better="up"
        note={t.ads.roasNote}
        hint={t.ads.roasNote}
      />
    </section>
  );
}

/** "Kết quả" do Facebook đếm, "Khách" do hệ thống ghi nhận: giải thích vì sao hai số lệch nhau. */
function ResultsVsLeads() {
  return (
    <details className="card card--tight explain" data-testid="ads-explain">
      <summary>{t.ads.explain.title}</summary>
      <ul>
        <li>{t.ads.explain.results}</li>
        <li>{t.ads.explain.leads}</li>
        <li>{t.ads.explain.why}</li>
      </ul>
    </details>
  );
}

function CostBars({ data }: { data: AdsReport }) {
  const limit = data.cost_threshold_vnd;
  const scale = Math.max(limit * 1.6, ...data.cost_bars.map((b) => b.cost_per_result_vnd));
  return (
    <div className="card card--tight">
      <div className="card__head">
        <h2>{t.ads.costTitle}</h2>
        <span>{format(t.ads.costHint, { v: formatMoney(limit) })}</span>
      </div>
      {data.cost_bars.length === 0 ? <p className="muted">{t.ads.costEmpty}</p> : null}
      <div className="cost-bars">
        {data.cost_bars.map((b) => {
          const over = b.cost_per_result_vnd > limit;
          return (
            <div className="cost-bar" key={b.id}>
              <span className="cost-bar__name" title={b.name}>
                {b.name}
              </span>
              <span className="cost-bar__track">
                <span
                  className={over ? "cost-bar__fill cost-bar__fill--over" : "cost-bar__fill"}
                  style={{ width: `${Math.min(100, (b.cost_per_result_vnd / scale) * 100)}%` }}
                />
                <span className="cost-bar__limit" aria-hidden="true" style={{ left: `${(limit / scale) * 100}%` }} />
              </span>
              <span className={over ? "cost-bar__value cost-bar__value--over" : "cost-bar__value"}>
                {formatMoney(b.cost_per_result_vnd)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ruleDescription(rule: AlertRule): string {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(rule.params)) {
    params[key] = key.endsWith("_vnd") ? formatMoney(value) : String(value).replace(".", ",");
  }
  return format(t.alerts.ruleDesc[rule.type], params);
}

function Rules() {
  const view = useAlertRules();
  const toggle = useToggleRule();
  const data = view.data;
  return (
    <div className="card card--tight" data-testid="ads-rules">
      <div className="card__head">
        <h2>{t.ads.rulesTitle}</h2>
      </div>
      {(data?.rules ?? [])
        .filter((r) => ALERT_RULES.includes(r.type))
        .map((rule) => (
          <div className="rule-row" key={rule.type}>
            <div>
              <b>{t.alerts.rules[rule.type]}</b>
              <span>{ruleDescription(rule)}</span>
            </div>
            <button
              type="button"
              role="switch"
              className="toggle-switch"
              aria-checked={rule.enabled}
              aria-label={t.alerts.rules[rule.type]}
              disabled={!data?.can_edit || toggle.isPending}
              onClick={() => toggle.mutate({ type: rule.type, enabled: !rule.enabled })}
            />
          </div>
        ))}
      {toggle.error instanceof ApiError ? <div className="alert alert--error">{errorMessage(toggle.error.code)}</div> : null}
      <span className="card__note">
        {t.ads.rulesNote} {data && !data.can_edit ? t.ads.rulesReadOnly : ""}
        {data && !data.chat_configured ? ` ${t.ads.rulesNoChat}` : ""}
      </span>
    </div>
  );
}

function statusOf(row: AdsRow, limit: number): { label: string; tone: "good" | "warn" | "neutral" } {
  if (row.status === "ACTIVE") {
    return row.cost_per_result_vnd !== null && row.cost_per_result_vnd > limit
      ? { label: t.ads.statuses.over, tone: "warn" }
      : { label: t.ads.statuses.ACTIVE, tone: "good" };
  }
  if (row.status === "PAUSED") return { label: t.ads.statuses.PAUSED, tone: "neutral" };
  return { label: row.status ?? t.ads.statuses.other, tone: "neutral" };
}

function objectiveLabel(objective: string | null): string {
  if (!objective) return "";
  return (t.ads.objectives as Record<string, string>)[objective] ?? objective;
}

function Table({ data, level, onLevel }: { data: AdsReport; level: AdsLevel; onLevel: (l: AdsLevel) => void }) {
  const limit = data.cost_threshold_vnd;
  return (
    <section className="card card--tight" style={{ padding: 0 }}>
      <div className="card__head" style={{ padding: "14px 18px 0" }}>
        <div className="segmented" role="tablist" aria-label={t.ads.levelsLabel}>
          {ADS_LEVELS.map((l) => (
            <button key={l} type="button" role="tab" aria-selected={level === l} aria-pressed={level === l} onClick={() => onLevel(l)}>
              {t.ads.levels[l]}
            </button>
          ))}
        </div>
      </div>
      <div className="table-wrap table-wrap--plain">
        <table data-testid="ads-table">
          <thead>
            <tr>
              <th scope="col">{t.ads.cols[level]}</th>
              <th scope="col">{t.ads.cols.status}</th>
              <th scope="col" className="num">{t.ads.cols.budget}</th>
              <th scope="col" className="num">{t.ads.cols.spend}</th>
              <th scope="col" className="num">{t.ads.cols.results}</th>
              <th scope="col" className="num">{t.ads.cols.cpr}</th>
              <th scope="col" className="num">{t.ads.cols.ctr}</th>
              <th scope="col" className="num">{t.ads.cols.cpm}</th>
              <th scope="col" className="num" title={t.reports.estimate}>{t.ads.cols.frequency}</th>
              <th scope="col" className="num">{t.ads.cols.leads}</th>
              <th scope="col" className="num">{t.ads.cols.won}</th>
              <th scope="col" className="num">{t.ads.cols.cpw}</th>
              <th scope="col" className="num" title={t.ads.roasNote}>{t.ads.cols.roas}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => {
              const status = statusOf(row, limit);
              const sub = [row.parent ?? row.account, objectiveLabel(row.objective)].filter(Boolean).join(" · ");
              return (
                <tr key={row.id} data-testid="ads-row">
                  <td>
                    <span className="name-cell">
                      <b>{row.name}</b>
                      <span>{sub}</span>
                    </span>
                  </td>
                  <td>
                    <StatusPill tone={status.tone}>{status.label}</StatusPill>
                  </td>
                  <td className="num">{formatMoney(row.daily_budget_vnd)}</td>
                  <td className="num">{formatMoney(row.spend_vnd)}</td>
                  <td className="num">{formatNumber(row.results)}</td>
                  <td className={row.cost_per_result_vnd !== null && row.cost_per_result_vnd > limit ? "num cell--bad" : "num"}>
                    {formatMoney(row.cost_per_result_vnd)}
                  </td>
                  <td className="num">{formatRate(row.ctr)}</td>
                  <td className="num">{formatMoney(row.cpm_vnd)}</td>
                  <td className="num">{frequencyText(row.frequency)}</td>
                  <td className="num">{formatNumber(row.leads)}</td>
                  <td className="num">{formatNumber(row.won)}</td>
                  <td className="num">
                    <b>{formatMoney(row.cost_per_won_vnd)}</b>
                  </td>
                  <td className="num">{formatRoas(row.roas)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data.rows.length === 0 ? <p className="muted" style={{ padding: 16 }}>{t.ads.empty}</p> : null}
      </div>
    </section>
  );
}

export function AdsPage() {
  const [range, setRange] = useState<RangeParams>({ range: "30d" });
  const [level, setLevel] = useState<AdsLevel>("campaign");
  const [accountId, setAccountId] = useState("");
  const report = useAdsReport(range, level, accountId);
  const data = report.data;

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.ads.title} />
          {data ? (
            <div className="page-sub">
              {format(t.ads.subtitle, {
                n: data.accounts.length,
                range: `${shortDate(data.range.first_day)} – ${shortDate(data.range.last_day)}`,
              })}
            </div>
          ) : null}
        </div>
        <div className="row-actions">
          {data && data.accounts.length > 1 ? (
            <label className="report-select">
              {t.ads.account}
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">{format(t.ads.allAccounts, { n: data.accounts.length })}</option>
                {data.accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <RangePicker keys={RANGE_KEYS} value={range} onChange={setRange} />
        </div>
      </div>
      {report.error instanceof ApiError ? (
        <div className="alert alert--error">{errorMessage(report.error.code, report.error.detail)}</div>
      ) : null}
      {!data ? (
        report.isLoading ? <div className="card muted">{t.reports.loading}</div> : null
      ) : (
        <>
          <MissingFx currencies={data.missing_fx} />
          <Kpis data={data} />
          <ResultsVsLeads />
          <section className="report-grid">
            <CostBars data={data} />
            <Rules />
          </section>
          <Table data={data} level={level} onLevel={setLevel} />
        </>
      )}
    </>
  );
}
