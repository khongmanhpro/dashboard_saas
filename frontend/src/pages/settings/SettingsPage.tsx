import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  CRITERIA,
  DEFAULT_WEIGHTS,
  useFormula,
  usePreview,
  useRecompute,
  useSaveFormula,
  type Formula,
  type Weights,
} from "../../api/staff";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime } from "../../leads/format";
import { formatScore, saveLabel, sameWeights, stepWeight, weightsTotal } from "../../staff/format";
import { TierBadge } from "../staff/StaffPage";

const MAX_BAR = 60;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

function FormulaEditor({ formula, timeZone }: { formula: Formula; timeZone: string }) {
  const [weights, setWeights] = useState<Weights>(formula.weights);
  const [message, setMessage] = useState<string | null>(null);
  const save = useSaveFormula();
  const recompute = useRecompute();
  const total = weightsTotal(weights);
  const changed = !sameWeights(weights, formula.weights);
  const state = saveLabel(total, changed);
  const editable = formula.can_edit;
  const debounced = useDebounced(weights, 300);
  const preview = usePreview(debounced, editable && weightsTotal(debounced) === 100);
  // Số xem thử chỉ đúng khi đã tính xong cho đúng bộ trọng số đang hiện.
  const previewStale =
    total !== 100 || !sameWeights(debounced, weights) || preview.isFetching || preview.isPlaceholderData;
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
                  save.mutate(weights, {
                    onSuccess: () => setMessage(t.settings.score.saved),
                  })
                }
              >
                {save.isPending ? t.settings.score.saving : state.label}
              </button>
              <button type="button" className="link-btn" onClick={() => setWeights(DEFAULT_WEIGHTS)}>
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
  return (
    <>
      <div className="page-top">
        <PageHeader title={t.settings.title} />
        <nav className="anchors">
          <a href="#score">{t.settings.anchors.score}</a>
        </nav>
      </div>
      {formula.data ? (
        <FormulaEditor formula={formula.data} timeZone={me.workspace.timezone} />
      ) : (
        <div className="muted">{t.app.loading}</div>
      )}
      <p className="note">{t.settings.laterNote}</p>
    </>
  );
}
