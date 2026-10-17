import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  CRITERIA,
  DEFAULT_THRESHOLDS,
  DEFAULT_WEIGHTS,
  useFormula,
  usePreview,
  useRecompute,
  useSaveFormula,
  type Criterion,
  type Formula,
  type Thresholds,
  type Weights,
} from "../../api/staff";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime } from "../../leads/format";
import {
  formatScore,
  saveLabel,
  sameThresholds,
  sameWeights,
  stepWeight,
  thresholdsValid,
  weightsTotal,
} from "../../staff/format";
import { TierBadge } from "../staff/StaffPage";
import { AlertsSection } from "./AlertsSection";

const MAX_BAR = 60;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

type Bound = { key: keyof Thresholds; unit: "percent" | "minutes" | "millionPerWeek" } | null;

/** Hai ô ngưỡng của mỗi tiêu chí (decisions.md mục K). Tốc độ: số phút càng nhỏ càng tốt. */
const BOUNDS: Record<Criterion, { zero: Bound; full: Bound; reversed?: boolean }> = {
  close_rate: { zero: { key: "close_rate_zero", unit: "percent" }, full: { key: "close_rate_full", unit: "percent" } },
  response_speed: {
    zero: { key: "speed_zero_minutes", unit: "minutes" },
    full: { key: "speed_full_minutes", unit: "minutes" },
    reversed: true,
  },
  revenue: { zero: null, full: { key: "revenue_full_vnd", unit: "millionPerWeek" } },
  phone_rate: { zero: { key: "phone_rate_zero", unit: "percent" }, full: { key: "phone_rate_full", unit: "percent" } },
  page_care: { zero: null, full: null },
  on_time: { zero: { key: "on_time_zero", unit: "percent" }, full: { key: "on_time_full", unit: "percent" } },
};

function ThresholdInput({
  bound,
  value,
  editable,
  label,
  onChange,
}: {
  bound: NonNullable<Bound>;
  value: number;
  editable: boolean;
  label: string;
  onChange: (v: number) => void;
}) {
  const million = bound.unit === "millionPerWeek";
  return (
    <label className="threshold-input">
      <span className="sr-only">{label}</span>
      <input
        type="number"
        min={0}
        step={million ? 0.5 : 1}
        disabled={!editable}
        aria-label={label}
        data-testid={`threshold-${bound.key}`}
        value={million ? value / 1_000_000 : value}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(million ? Math.round(n * 1_000_000) : Math.round(n));
        }}
      />
      <span>{t.settings.score.units[bound.unit]}</span>
    </label>
  );
}

function ThresholdEditor({
  thresholds,
  setThresholds,
  editable,
  postsTarget,
}: {
  thresholds: Thresholds;
  setThresholds: (fn: (th: Thresholds) => Thresholds) => void;
  editable: boolean;
  postsTarget: number;
}) {
  const s = t.settings.score;
  return (
    <div className="thresholds" data-testid="thresholds">
      <b>{s.thresholdsTitle}</b>
      <span className="note">{s.thresholdsHint}</span>
      {CRITERIA.map((c) => {
        const b = BOUNDS[c];
        const name = t.staffDetail.parts[c];
        const set = (key: keyof Thresholds) => (v: number) => setThresholds((th) => ({ ...th, [key]: v }));
        return (
          <div key={c} className="threshold-row">
            <span className="threshold-row__name">{name}</span>
            {c === "page_care" ? (
              <span className="note">{format(s.pageCareNote, { n: postsTarget })}</span>
            ) : (
              <>
                <span className="threshold-row__cell">
                  {s.zeroAt} {b.reversed ? s.atLeast : s.atMost}{" "}
                  {b.zero ? (
                    <ThresholdInput
                      bound={b.zero}
                      value={thresholds[b.zero.key]}
                      editable={editable}
                      label={`${name}: ${s.zeroAt}`}
                      onChange={set(b.zero.key)}
                    />
                  ) : (
                    <b>{s.revenueZero}</b>
                  )}
                </span>
                <span className="threshold-row__cell">
                  {s.fullAt} {b.reversed ? s.atMost : s.atLeast}{" "}
                  {b.full ? (
                    <ThresholdInput
                      bound={b.full}
                      value={thresholds[b.full.key]}
                      editable={editable}
                      label={`${name}: ${s.fullAt}`}
                      onChange={set(b.full.key)}
                    />
                  ) : null}
                  {c === "revenue" ? <span className="note">{s.revenueNote}</span> : null}
                </span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function FormulaEditor({ formula, timeZone }: { formula: Formula; timeZone: string }) {
  const [weights, setWeights] = useState<Weights>(formula.weights);
  const [thresholds, setThresholds] = useState<Thresholds>(formula.thresholds);
  const [message, setMessage] = useState<string | null>(null);
  const save = useSaveFormula();
  const recompute = useRecompute();
  const total = weightsTotal(weights);
  const valid = thresholdsValid(thresholds);
  const changed = !sameWeights(weights, formula.weights) || !sameThresholds(thresholds, formula.thresholds);
  const state = saveLabel(total, changed, valid);
  const editable = formula.can_edit;
  const debounced = useDebounced({ weights, thresholds }, 300);
  const preview = usePreview(
    debounced,
    editable && weightsTotal(debounced.weights) === 100 && thresholdsValid(debounced.thresholds),
  );
  // Số xem thử chỉ đúng khi đã tính xong cho đúng bộ trọng số và ngưỡng đang hiện.
  const previewStale =
    total !== 100 ||
    !valid ||
    !sameWeights(debounced.weights, weights) ||
    !sameThresholds(debounced.thresholds, thresholds) ||
    preview.isFetching ||
    preview.isPlaceholderData;
  const p = { a: formula.tier_a, b: formula.tier_b, c: formula.tier_c, a1: formula.tier_a - 1, b1: formula.tier_b - 1 };
  const error = save.error ?? recompute.error;

  return (
    <section id="score" className="card" aria-labelledby="score-title">
      <div className="section-head section-head--row">
        <div>
          <h2 id="score-title">{t.settings.score.title}</h2>
          <span>{format(t.settings.score.hint, p)}</span>
          <span>
            {format(t.settings.score.version, {
              v: formula.version,
              method: t.settings.score.methods[formula.score_method],
              time: formatDateTime(formula.effective_from, timeZone),
            })}
          </span>
        </div>
        <span className={total === 100 ? "total-pill total-pill--ok" : "total-pill total-pill--bad"} data-testid="weights-total">
          {format(t.settings.score.total, { n: total })}
        </span>
      </div>
      <div className="formula">
        <div className="weights">
          {CRITERIA.map((c) => (
            <div key={c} className="weight-row">
              <span className="weight-row__text">
                <b>{t.staffDetail.parts[c]}</b>
                <span>{t.settings.score.desc[c]}</span>
              </span>
              <span className="weight-row__bar" aria-hidden="true">
                <span style={{ width: `${Math.min(100, (weights[c] / MAX_BAR) * 100)}%` }} />
              </span>
              <div className="stepper" role="group" aria-label={format(t.settings.score.weightGroup, { name: t.staffDetail.parts[c] })}>
                <button
                  type="button"
                  aria-label={t.settings.score.decrease}
                  disabled={!editable || weights[c] <= 0}
                  onClick={() => setWeights((w) => stepWeight(w, c, -5))}
                >
                  −
                </button>
                <span data-testid={`weight-${c}`}>{weights[c]}%</span>
                <button
                  type="button"
                  aria-label={t.settings.score.increase}
                  disabled={!editable || weights[c] >= 100}
                  onClick={() => setWeights((w) => stepWeight(w, c, 5))}
                >
                  +
                </button>
              </div>
            </div>
          ))}
          <ThresholdEditor
            thresholds={thresholds}
            setThresholds={setThresholds}
            editable={editable}
            postsTarget={formula.posts_per_week_target}
          />
        </div>
        <aside className={previewStale ? "preview preview--stale" : "preview"} aria-busy={previewStale}>
          {editable ? (
            <>
              <b>{t.settings.score.previewTitle}</b>
              {preview.data && preview.data.rows.length === 0 ? (
                <span className="note">{t.settings.score.previewEmpty}</span>
              ) : null}
              {preview.data?.rows.slice(0, 5).map((row) => (
                <div key={row.member.id} className="preview__row" data-testid="preview-row">
                  <span>{row.member.name}</span>
                  <span>
                    <span className="muted">{formatScore(row.current_total)} →</span>{" "}
                    <b data-testid="preview-new">{formatScore(row.new_total)}</b> <TierBadge tier={row.new_tier} />
                  </span>
                </div>
              ))}
              <span className="note">{t.settings.score.previewHint}</span>
              <button
                type="button"
                className={state.ok ? "btn btn--primary" : "btn btn--warn"}
                disabled={!state.ok || save.isPending}
                onClick={() =>
                  save.mutate({ weights, thresholds }, {
                    onSuccess: () => setMessage(t.settings.score.saved),
                  })
                }
              >
                {save.isPending ? t.settings.score.saving : state.label}
              </button>
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  setWeights(DEFAULT_WEIGHTS);
                  setThresholds(DEFAULT_THRESHOLDS);
                }}
              >
                {t.settings.score.reset}
              </button>
              <button
                type="button"
                className="btn"
                disabled={recompute.isPending}
                onClick={() => recompute.mutate(undefined, { onSuccess: () => setMessage(t.settings.score.recomputed) })}
              >
                {recompute.isPending ? t.staff.recomputing : t.staff.recompute}
              </button>
            </>
          ) : (
            <span className="note">{t.settings.score.readOnly}</span>
          )}
          {message ? (
            <div className="alert alert--ok" role="status">
              {message}
            </div>
          ) : null}
          {error instanceof ApiError ? (
            <div className="alert alert--error" role="alert">
              {errorMessage(error.code)}
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

export function SettingsPage() {
  const me = useOutletContext<Me>();
  const formula = useFormula();
  const canAlerts = "settings.manage" in me.permissions;
  return (
    <>
      <div className="page-top">
        <PageHeader title={t.settings.title} />
        <nav className="anchors">
          <a href="#score">{t.settings.anchors.score}</a>
          {canAlerts ? <a href="#alerts">{t.settings.anchors.alerts}</a> : null}
          {canAlerts ? <a href="#fx">{t.settings.anchors.fx}</a> : null}
        </nav>
      </div>
      {formula.data ? (
        <FormulaEditor formula={formula.data} timeZone={me.workspace.timezone} />
      ) : (
        <div className="muted">{t.app.loading}</div>
      )}
      {canAlerts ? <AlertsSection timeZone={me.workspace.timezone} /> : null}
      <p className="note">{t.settings.laterNote}</p>
    </>
  );
}
