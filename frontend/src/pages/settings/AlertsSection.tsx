import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import {
  RULE_TYPES,
  useAddFxRate,
  useAlertSettings,
  useDeleteFxRate,
  useSaveAlertSettings,
  useSendTestAlert,
  type AlertRule,
  type AlertSettings,
} from "../../api/reports";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime, groupThousands } from "../../leads/format";

function errorText(error: unknown): string | null {
  if (!error) return null;
  return error instanceof ApiError ? errorMessage(error.code, error.detail) : t.errors.unknown;
}

function RuleEditor({
  rule,
  onChange,
}: {
  rule: AlertRule;
  onChange: (rule: AlertRule) => void;
}) {
  const params = Object.keys(rule.params) as (keyof typeof t.alerts.params)[];
  return (
    <div className="rule-row">
      <div>
        <b>{t.alerts.rules[rule.type]}</b>
        <span>
          {format(
            t.alerts.ruleDesc[rule.type],
            Object.fromEntries(
              params.map((k) => [k, k === "max" ? String(rule.params[k] ?? 0).replace(".", ",") : groupThousands(rule.params[k] ?? 0)]),
            ),
          )}
        </span>
        {params.length ? (
          <span className="rule-params">
            {params.map((key) => (
              <label key={key} className="report-select">
                {t.alerts.params[key]}
                <input
                  type="number"
                  min={0}
                  step={key === "max" ? 0.1 : 1000}
                  value={rule.params[key] ?? 0}
                  onChange={(e) => onChange({ ...rule, params: { ...rule.params, [key]: Number(e.target.value) } })}
                  style={{ width: 130 }}
                />
              </label>
            ))}
          </span>
        ) : null}
      </div>
      <button
        type="button"
        role="switch"
        className="switch"
        aria-checked={rule.enabled}
        aria-label={t.alerts.rules[rule.type]}
        onClick={() => onChange({ ...rule, enabled: !rule.enabled })}
      />
    </div>
  );
}

function FxRates({ data }: { data: AlertSettings }) {
  const add = useAddFxRate();
  const remove = useDeleteFxRate();
  const [currency, setCurrency] = useState(data.currencies[0] ?? "USD");
  const [from, setFrom] = useState(new Date().toISOString().slice(0, 10));
  const [rate, setRate] = useState("");
  const error = errorText(add.error ?? remove.error);
  return (
    <div className="card card--tight" id="fx">
      <div className="card__head">
        <h2>{t.alerts.fxTitle}</h2>
      </div>
      <p className="card__note">
        {t.alerts.fxHint}{" "}
        {data.currencies.length ? format(t.alerts.fxCurrencies, { list: data.currencies.join(", ") }) : t.alerts.fxNone}
      </p>
      <form
        className="row-actions"
        onSubmit={(e) => {
          e.preventDefault();
          if (!rate) return;
          add.mutate({ currency: currency.toUpperCase(), effective_from: from, vnd_per_unit: rate }, { onSuccess: () => setRate("") });
        }}
      >
        <label className="report-select">
          {t.alerts.fxCurrency}
          <input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} style={{ width: 80 }} />
        </label>
        <label className="report-select">
          {t.alerts.fxFrom}
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="report-select">
          {t.alerts.fxRate}
          <input type="number" min={0} step="0.0001" value={rate} onChange={(e) => setRate(e.target.value)} style={{ width: 130 }} />
        </label>
        <button type="submit" className="btn" disabled={add.isPending || !rate}>
          {t.alerts.fxAdd}
        </button>
      </form>
      {error ? <div className="alert alert--error">{error}</div> : null}
      {data.fx_rates.length === 0 ? (
        <p className="muted">{t.alerts.fxEmpty}</p>
      ) : (
        <table className="mini-table" data-testid="fx-table">
          <thead>
            <tr>
              <th scope="col">{t.alerts.fxCurrency}</th>
              <th scope="col">{t.alerts.fxFrom}</th>
              <th scope="col">{t.alerts.fxRate}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.fx_rates.map((r) => (
              <tr key={r.id}>
                <td>{r.currency}</td>
                <td>{r.effective_from.split("-").reverse().join("/")}</td>
                <td>{groupThousands(Number(r.vnd_per_unit))}</td>
                <td>
                  <button type="button" className="btn" disabled={remove.isPending} onClick={() => remove.mutate(r.id)}>
                    {t.alerts.fxDelete}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function AlertsSection({ timeZone }: { timeZone: string }) {
  const settings = useAlertSettings(true);
  const save = useSaveAlertSettings();
  const test = useSendTestAlert();
  const data = settings.data;
  const [chatId, setChatId] = useState("");
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setChatId(data.chat_id ?? "");
    setRules(RULE_TYPES.map((type) => data.rules.find((r) => r.type === type)).filter((r): r is AlertRule => Boolean(r)));
  }, [data]);

  if (!data) return <div className="muted">{t.app.loading}</div>;
  const error = errorText(save.error ?? test.error);

  return (
    <>
      <section id="alerts" className="card" aria-labelledby="alerts-title">
        <div className="section-head">
          <h2 id="alerts-title">{t.alerts.title}</h2>
          {data.is_mock ? <span>{t.alerts.mockNote}</span> : !data.bot_configured ? <span>{t.alerts.botMissing}</span> : null}
        </div>
        <div className="field">
          <label htmlFor="chat-id">{t.alerts.chatId}</label>
          <input id="chat-id" value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="-100…" />
          <span className="field__hint">{t.alerts.chatHint}</span>
        </div>
        <p className="card__note">{t.alerts.emailLater}</p>
        <h3 className="subhead">{t.alerts.rulesTitle}</h3>
        <div data-testid="alert-rules">
          {rules.map((rule) => (
            <RuleEditor key={rule.type} rule={rule} onChange={(next) => setRules((rs) => rs.map((r) => (r.type === next.type ? next : r)))} />
          ))}
        </div>
        {error ? <div className="alert alert--error">{error}</div> : null}
        {message ? <div className="notice notice--info" role="status">{message}</div> : null}
        <div className="row-actions" style={{ marginTop: 12 }}>
          <button
            type="button"
            className="btn btn--primary"
            disabled={save.isPending}
            onClick={() => {
              setMessage(null);
              test.reset();
              save.mutate({ chat_id: chatId.trim() || null, rules }, { onSuccess: () => setMessage(t.alerts.saved) });
            }}
          >
            {t.alerts.save}
          </button>
          <button
            type="button"
            className="btn"
            disabled={test.isPending || !data.chat_id}
            onClick={() => {
              setMessage(null);
              save.reset();
              test.mutate(undefined, {
                onSuccess: (r) => setMessage(r.status === "mock" ? t.alerts.testMock : t.alerts.testSent),
              });
            }}
          >
            {t.alerts.test}
          </button>
        </div>
        <h3 className="subhead">{t.alerts.deliveriesTitle}</h3>
        {data.deliveries.length === 0 ? (
          <p className="muted">{t.alerts.deliveriesEmpty}</p>
        ) : (
          <table className="mini-table">
            <tbody>
              {data.deliveries.map((d, i) => (
                <tr key={i}>
                  <td>{t.alerts.rules[d.rule_type]}</td>
                  <td>{t.alerts.deliveryStatus[d.status]}</td>
                  <td>{formatDateTime(d.sent_at, timeZone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <FxRates data={data} />
    </>
  );
}
