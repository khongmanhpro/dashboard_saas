import { useState } from "react";

import { ApiError } from "../../api/client";
import { useCheckToken, useConnectBm, useRotateToken, type Bm, type CheckItem, type CheckResult } from "../../api/bms";
import { usePublicConfig } from "../../auth/useAuth";
import { errorMessage, format, t } from "../../i18n";

const BUSINESS_SETTINGS_URL = "https://business.facebook.com/settings/system-users";

function checkText(item: CheckItem, result: CheckResult): { label: string; sub: string | null } {
  const w = t.bm.wizard;
  const label = format(w.checks[item.key], { count: item.count ?? 0, total: item.total ?? 0 });
  let sub: string | null = null;
  if (item.key === "token_valid") {
    sub = format(w.checkDetail.token_valid, { name: result.system_user_name ?? "", bm: result.business_name });
  } else if (item.key === "leadgen" && item.level !== "ok") sub = w.checkDetail.leadgen_warn;
  else if (item.key === "ad_accounts" && item.level !== "ok") sub = w.checkDetail.ads_warn;
  else if (item.key === "webhooks" && item.level === "fail") sub = w.checkDetail.webhooks_fail;
  else if (item.key === "pages" && item.level === "fail") sub = w.checkDetail.pages_fail;
  else if (item.key === "other_scopes") sub = item.detail;
  return { label, sub };
}

/** Khung thêm BM 4 bước (BMs.dc.html). `rotate` có giá trị thì là cập nhật mã cho BM đã có. */
export function AddBmPanel({ rotate, onClose }: { rotate: Bm | null; onClose: () => void }) {
  const [step, setStep] = useState(rotate ? 2 : 0);
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [businessId, setBusinessId] = useState(rotate?.fb_business_id ?? "");
  const [done, setDone] = useState<string | null>(null);
  const check = useCheckToken();
  const connect = useConnectBm();
  const rotateMutation = useRotateToken(rotate?.id ?? "");
  const config = usePublicConfig();
  const w = t.bm.wizard;
  const body = { token: token.trim(), fb_business_id: businessId.trim() || undefined, name: name.trim() || undefined };
  const save = rotate ? rotateMutation : connect;
  const result = check.data;
  const error = check.error ?? save.error;

  const next = () => {
    if (step < 2) setStep(step + 1);
    else if (step === 2) check.mutate(body, { onSuccess: () => setStep(3) });
    else
      save.mutate(rotate ? { token: body.token } : body, {
        onSuccess: (bm) => {
          setToken(""); // không giữ mã trong bộ nhớ trang lâu hơn cần thiết
          setDone(format(w.saved, { name: bm.name }));
        },
      });
  };
  const busy = check.isPending || save.isPending;
  const nextDisabled = busy || (step === 2 && body.token.length < 8) || (step === 3 && !result?.can_save);

  return (
    <aside className="card bm-panel" aria-labelledby="add-bm-title">
      <div className="section-head section-head--row">
        <h2 id="add-bm-title">{rotate ? format(w.rotateTitle, { name: rotate.name }) : w.title}</h2>
        <button type="button" className="link-btn" aria-label={w.close} onClick={onClose}>
          ×
        </button>
      </div>
      {done ? (
        <>
          <div className="alert alert--ok" role="status">
            {done}
          </div>
          <button type="button" className="btn btn--block" onClick={onClose}>
            {w.close}
          </button>
        </>
      ) : (
        <>
          <ol className="steps" aria-label={w.title}>
            {w.steps.map((label, i) => (
              <li key={label} aria-current={i === step ? "step" : undefined} className={i < step ? "steps__done" : undefined}>
                {i + 1}. {label}
              </li>
            ))}
          </ol>
          {step === 0 ? (
            <div className="m-stack">
              <p>{w.step0}</p>
              <a href={BUSINESS_SETTINGS_URL} target="_blank" rel="noopener noreferrer">
                {w.step0Link} <span aria-hidden="true">↗</span>
              </a>
              <p className="note">{w.step0Note}</p>
            </div>
          ) : null}
          {step === 1 ? (
            <div className="m-stack">
              <p>{w.step1}</p>
              <ul className="task-list">
                {w.tasks.map(([a, b]) => (
                  <li key={a}>
                    <span aria-hidden="true">✓</span>
                    <span>
                      <b>{a}</b> <span className="muted">· {b}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="note">{w.step1Note}</p>
            </div>
          ) : null}
          {step === 2 ? (
            <div className="m-stack">
              <p>{w.step2}</p>
              {!rotate ? (
                <div className="field">
                  <label htmlFor="bm-name">{w.name}</label>
                  <input id="bm-name" value={name} placeholder={w.namePlaceholder} onChange={(e) => setName(e.target.value)} />
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="bm-token">{w.token}</label>
                <input
                  id="bm-token"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </div>
              {!rotate ? (
                <div className="field">
                  <label htmlFor="bm-id">{w.businessId}</label>
                  <input id="bm-id" inputMode="numeric" value={businessId} onChange={(e) => setBusinessId(e.target.value)} />
                </div>
              ) : null}
              <p className="note">{w.tokenNote}</p>
              {config.data?.mock_mode ? <p className="note">{w.mockHint}</p> : null}
            </div>
          ) : null}
          {step === 3 && result ? (
            <div className="m-stack" data-testid="bm-checks">
              {result.checks.map((item) => {
                const text = checkText(item, result);
                return (
                  <div key={item.key} className="check-row">
                    <span className={`check-mark check-mark--${item.level}`} aria-hidden="true">
                      {item.level === "ok" ? "✓" : item.level === "warn" ? "!" : "✕"}
                    </span>
                    <span>
                      <b>{text.label}</b>
                      {text.sub ? <span className="note">{text.sub}</span> : null}
                    </span>
                  </div>
                );
              })}
              <p className="note">
                {format(w.summary, {
                  pages: result.pages.length,
                  fresh: result.pages.filter((p) => p.state === "new").length,
                })}
              </p>
              {result.pages.some((p) => p.state === "other_workspace") ? (
                <p className="note">
                  {format(w.otherWorkspace, { n: result.pages.filter((p) => p.state === "other_workspace").length })}
                </p>
              ) : null}
              {result.already_connected && !rotate ? <p className="note">{w.alreadyConnected}</p> : null}
              {!result.can_save ? (
                <div className="alert alert--error" role="alert">
                  {w.cannotSave}
                </div>
              ) : null}
            </div>
          ) : null}
          {error instanceof ApiError ? (
            <div className="alert alert--error" role="alert">
              {errorMessage(error.code)}
            </div>
          ) : null}
          <div className="bm-panel__actions">
            <button type="button" className="btn" disabled={step === 0 || busy} onClick={() => setStep(step - 1)}>
              {w.back}
            </button>
            <button type="button" className="btn btn--primary" disabled={nextDisabled} onClick={next}>
              {busy ? (step === 3 ? w.saving : w.checking) : w.next[step]}
            </button>
          </div>
          {!rotate ? (
            <p className="note bm-panel__later">
              {w.later} <span className="tag">{w.laterTag}</span>
            </p>
          ) : null}
        </>
      )}
    </aside>
  );
}
