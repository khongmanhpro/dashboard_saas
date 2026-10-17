import { useState } from "react";
import { Link, Navigate, useOutletContext, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  LOST_REASONS,
  useLead,
  useSetCalled,
  useSetResult,
  type LeadDetail,
  type LeadStatus,
  type TimelineItem,
} from "../../api/leads";
import { useRemind } from "../../api/mobile";
import type { Me } from "../../api/types";
import { usePublicConfig } from "../../auth/useAuth";
import { errorMessage, format, t } from "../../i18n";
import {
  displayName,
  EMPTY_RESULT_FORM,
  formatDateTime,
  formatDuration,
  formatVnd,
  groupThousands,
  initials,
  isoToZonedLocal,
  parseVndInput,
  sourceLabel,
  validateResultForm,
  type ResultForm,
} from "../../leads/format";

// Đường dẫn hộp thư của Trang trong Business Suite. Đường dẫn tới đúng hội thoại kiểm tra lại
// khi ứng dụng Meta đã Live (quyết định Bước 3).
export function inboxUrl(fbPageId: string): string {
  return `https://business.facebook.com/latest/inbox/all?asset_id=${encodeURIComponent(fbPageId)}`;
}

function statusLabel(value: unknown): string {
  return typeof value === "string" && value in t.leads.status ? t.leads.status[value as LeadStatus] : String(value);
}

interface Row {
  icon: string;
  iconTone: string;
  who: string;
  tag?: { text: string; tone: string };
  body: string;
  bubble?: "customer" | "page";
}

function describe(item: TimelineItem, lead: LeadDetail, timeZone: string): Row {
  if (item.kind === "message") {
    const text = item.text ?? (item.has_attachments ? t.lead.attachment : "");
    if (item.direction === "in") {
      return { icon: "K", iconTone: "", who: t.lead.who.customer, body: text, bubble: "customer" };
    }
    let tag: Row["tag"];
    if (item.is_first_reply && lead.response_business_seconds !== null) {
      tag = {
        text: format(t.lead.firstReplyTag, { time: formatDuration(lead.response_business_seconds) }),
        tone: lead.is_slow ? "tag--bad" : "tag--good",
      };
    } else if (item.is_automated) {
      tag = { text: t.lead.automated, tone: "" };
    }
    return {
      icon: initials(lead.page.name) || "T",
      iconTone: "timeline__icon--page",
      who: lead.page.name,
      tag,
      body: text,
      bubble: "page",
    };
  }
  const who = item.actor ?? t.lead.who.system;
  const data = item.data ?? {};
  const note = typeof data.note === "string" ? ` ${format(t.lead.events.note, { note: data.note })}` : "";
  switch (item.type) {
    case "created": {
      const body =
        data.source === "leadgen"
          ? t.lead.events.createdForm
          : data.owner_member_id
            ? t.lead.events.created
            : t.lead.events.createdNoOwner;
      const tag = lead.from_ad ? { text: t.lead.events.fromAd, tone: "tag--sample" } : undefined;
      return { icon: "★", iconTone: "timeline__icon--system", who, tag, body };
    }
    case "replied":
      return { icon: "↩", iconTone: "timeline__icon--page", who, body: t.lead.events.replied };
    case "phone_detected":
      return {
        icon: "✓",
        iconTone: "timeline__icon--good",
        who,
        tag: { text: t.lead.events.phoneTag, tone: "tag--good" },
        body: t.lead.events.phone_detected,
      };
    case "called":
      return {
        icon: "☎",
        iconTone: "timeline__icon--page",
        who,
        body: data.called ? t.lead.events.calledOn : t.lead.events.calledOff,
      };
    case "status_changed": {
      let extra = "";
      if (typeof data.won_value_vnd === "number") extra = ` ${formatVnd(data.won_value_vnd)}.`;
      if (typeof data.lost_reason === "string" && data.lost_reason in t.leads.lostReasons) {
        extra = ` ${format(t.leads.lostReasonLine, {
          reason: t.leads.lostReasons[data.lost_reason as keyof typeof t.leads.lostReasons],
        })}.`;
      }
      if (typeof data.callback_at === "string") extra = ` ${formatDateTime(data.callback_at, timeZone)}.`;
      return {
        icon: "●",
        iconTone: "timeline__icon--page",
        who,
        body: format(t.lead.events.status_changed, { from: statusLabel(data.from), to: statusLabel(data.to) }) + extra + note,
      };
    }
    case "merged":
      return { icon: "⇄", iconTone: "timeline__icon--system", who, body: t.lead.events.merged };
    case "overdue":
      return {
        icon: "!",
        iconTone: "timeline__icon--bad",
        who: t.lead.who.system,
        tag: { text: t.lead.events.overdueTag, tone: "tag--bad" },
        body: t.lead.events.overdue,
      };
    default:
      return { icon: "•", iconTone: "", who, body: item.type ?? "" };
  }
}

export function Timeline({ lead, timeZone }: { lead: LeadDetail; timeZone: string }) {
  return (
    <section className="card" aria-labelledby="timeline-title">
      <div className="section-head">
        <h2 id="timeline-title">{t.lead.timelineTitle}</h2>
        <span>{t.lead.timelineHint}</span>
      </div>
      {lead.timeline_truncated ? (
        <p className="note">{format(t.lead.timelineTruncated, { n: 200 })}</p>
      ) : null}
      <ol className="timeline">
        {lead.timeline.map((item, i) => {
          const row = describe(item, lead, timeZone);
          return (
            <li key={`${item.at}-${i}`}>
              <div className="timeline__rail">
                <span className={`timeline__icon ${row.iconTone}`} aria-hidden="true">
                  {row.icon}
                </span>
                <span className="timeline__line" aria-hidden="true" />
              </div>
              <div className="timeline__body">
                <div className="timeline__meta">
                  <b>{row.who}</b>
                  <time dateTime={item.at}>{formatDateTime(item.at, timeZone)}</time>
                  {row.tag ? <span className={`tag ${row.tag.tone}`}>{row.tag.text}</span> : null}
                </div>
                <div className={row.bubble ? `bubble ${row.bubble === "page" ? "bubble--page" : ""}` : "note"}>
                  {row.body}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function initialForm(lead: LeadDetail, timeZone: string): ResultForm {
  if (lead.status === "won") {
    return { ...EMPTY_RESULT_FORM, status: "won", wonValue: groupThousands(lead.won_value_vnd ?? 0) };
  }
  if (lead.status === "callback" && lead.callback_at) {
    return { ...EMPTY_RESULT_FORM, status: "callback", callbackLocal: isoToZonedLocal(lead.callback_at, timeZone) };
  }
  if (lead.status === "lost") {
    return { ...EMPTY_RESULT_FORM, status: "lost", lostReason: lead.lost_reason, note: lead.lost_note ?? "" };
  }
  return EMPTY_RESULT_FORM;
}

export function ResultPanel({ lead, timeZone }: { lead: LeadDetail; timeZone: string }) {
  const [form, setForm] = useState<ResultForm>(() => initialForm(lead, timeZone));
  const [saved, setSaved] = useState(false);
  const setCalled = useSetCalled(lead.id);
  const setResult = useSetResult(lead.id);
  const check = validateResultForm(form, timeZone);
  const editable = lead.permissions.can_edit_result;
  const now = Date.now();
  const due = Date.parse(lead.result_due_at);

  let deadline: string;
  if (lead.result_at) deadline = format(t.lead.result.doneAt, { time: formatDateTime(lead.result_at, timeZone) });
  else if (due >= now) deadline = format(t.lead.result.dueIn, { time: formatDuration((due - now) / 1000) });
  else deadline = format(t.lead.result.overdueBy, { time: formatDuration((now - due) / 1000) });

  const update = (patch: Partial<ResultForm>) => {
    setSaved(false);
    setForm((f) => ({ ...f, ...patch }));
  };
  const error = setResult.error ?? setCalled.error;

  return (
    <section className="card result-form" aria-labelledby="result-title">
      <div className="section-head">
        <h2 id="result-title">{t.lead.result.title}</h2>
        <span>{deadline}</span>
      </div>
      <div className="switch-row">
        <span className="switch-row__text">
          {t.lead.result.calledLabel}
          <span>{lead.phone ? format(t.lead.result.phoneFrom, { phone: lead.phone }) : t.lead.result.noPhone}</span>
        </span>
        <button
          type="button"
          role="switch"
          className="switch"
          aria-checked={lead.called_at !== null}
          aria-label={t.lead.result.calledLabel}
          disabled={setCalled.isPending}
          onClick={() => setCalled.mutate(lead.called_at === null)}
        />
      </div>

      <div className="result-buttons" role="group" aria-label={t.lead.result.group}>
        {(["won", "callback", "lost"] as const).map((kind) => (
          <button
            key={kind}
            type="button"
            data-kind={kind}
            aria-pressed={form.status === kind}
            disabled={!editable}
            onClick={() => update({ status: form.status === kind ? null : kind })}
          >
            {t.leads.status[kind]}
          </button>
        ))}
      </div>

      {form.status === "won" ? (
        <div className="field">
          <label htmlFor="won-value">{t.lead.result.wonValue}</label>
          <span className="money-input">
            <input
              id="won-value"
              inputMode="numeric"
              autoComplete="off"
              value={form.wonValue}
              disabled={!editable}
              onChange={(e) => {
                const value = parseVndInput(e.target.value);
                update({ wonValue: value === null ? "" : groupThousands(value) });
              }}
            />
            <span>{t.lead.result.currency}</span>
          </span>
        </div>
      ) : null}

      {form.status === "callback" ? (
        <div className="field">
          <label htmlFor="callback-at">{t.lead.result.callbackAt}</label>
          <input
            id="callback-at"
            type="datetime-local"
            value={form.callbackLocal}
            disabled={!editable}
            onChange={(e) => update({ callbackLocal: e.target.value })}
          />
        </div>
      ) : null}

      {form.status === "lost" ? (
        <div className="field">
          <span>{t.lead.result.lostReason}</span>
          <div className="reason-buttons" role="group" aria-label={t.lead.result.lostReason}>
            {LOST_REASONS.map((reason) => (
              <button
                key={reason}
                type="button"
                aria-pressed={form.lostReason === reason}
                disabled={!editable}
                onClick={() => update({ lostReason: reason })}
              >
                {t.leads.lostReasons[reason]}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="field">
        <label htmlFor="result-note">{t.lead.result.note}</label>
        <textarea
          id="result-note"
          rows={2}
          maxLength={500}
          value={form.note}
          disabled={!editable}
          placeholder={t.lead.result.notePlaceholder}
          onChange={(e) => update({ note: e.target.value })}
        />
      </div>

      {error ? (
        <div className="alert alert--error" role="alert">
          {error instanceof ApiError ? errorMessage(error.code, error.detail) : t.errors.unknown}
        </div>
      ) : null}
      {saved ? (
        <div className="alert alert--ok" role="status">
          {t.lead.result.saved}
        </div>
      ) : null}

      <button
        type="button"
        className="btn btn--primary btn--block"
        disabled={!editable || !check.ok || setResult.isPending}
        onClick={() => {
          if (!check.ok) return;
          setResult.mutate(check.body, { onSuccess: () => setSaved(true) });
        }}
      >
        {setResult.isPending ? t.lead.result.saving : check.ok ? t.lead.result.save : check.label}
      </button>
      {lead.permissions.edit_until && editable ? (
        <p className="note">
          {format(t.lead.result.editUntil, { time: formatDateTime(lead.permissions.edit_until, timeZone) })}
        </p>
      ) : null}
      {!editable ? <p className="note">{t.lead.result.editClosed}</p> : null}
    </section>
  );
}

export function RemindPanel({ lead }: { lead: LeadDetail }) {
  const remind = useRemind(lead.id);
  return (
    <section className="card result-form" aria-label={t.lead.result.remind}>
      <button type="button" className="btn btn--block" disabled={remind.isPending} onClick={() => remind.mutate()}>
        {remind.isPending ? t.lead.result.reminding : t.lead.result.remind}
      </button>
      {remind.isSuccess ? (
        <div className="alert alert--ok" role="status">
          {t.lead.result.reminded}
        </div>
      ) : null}
      {remind.error instanceof ApiError ? (
        <div className="alert alert--error" role="alert">
          {errorMessage(remind.error.code)}
        </div>
      ) : null}
    </section>
  );
}

export function SourcePanel({ lead }: { lead: LeadDetail }) {
  let firstReply: string;
  if (lead.source === "leadgen") firstReply = t.lead.source.notMeasured;
  else if (lead.response_business_seconds === null) firstReply = t.lead.source.notReplied;
  else {
    const threshold = lead.is_slow ? t.lead.source.overThreshold : t.lead.source.underThreshold;
    firstReply = `${formatDuration(lead.response_business_seconds)} · ${format(threshold, { m: lead.slow_reply_minutes })}`;
  }
  return (
    <section className="card" aria-labelledby="source-title">
      <div className="section-head">
        <h2 id="source-title">{t.lead.source.title}</h2>
      </div>
      <dl className="dl">
        <dt>{t.lead.source.channel}</dt>
        <dd>{sourceLabel({ ...lead, status: "new" })}</dd>
        {lead.fb_ad_id ? (
          <>
            <dt>{t.lead.source.adId}</dt>
            <dd>{lead.fb_ad_id}</dd>
          </>
        ) : null}
        <dt>{t.lead.source.firstReply}</dt>
        <dd className={lead.is_slow ? "timer--hot" : undefined}>{firstReply}</dd>
        {lead.campaign_name ? (
          <>
            <dt>{t.lead.source.campaign}</dt>
            <dd>{lead.campaign_name}</dd>
          </>
        ) : null}
        {lead.cost_visible ? (
          <>
            <dt>{t.lead.source.cost}</dt>
            {lead.estimated_cost_vnd !== null ? (
              <dd title={t.lead.source.costHint}>{formatVnd(lead.estimated_cost_vnd)}</dd>
            ) : (
              <dd className="muted">{lead.campaign_name ? t.lead.source.costNoSpend : t.lead.source.costOrganic}</dd>
            )}
          </>
        ) : null}
      </dl>
    </section>
  );
}

export function LeadDetailPage() {
  const { id = "" } = useParams();
  const me = useOutletContext<Me>();
  const timeZone = me.workspace.timezone;
  const lead = useLead(id);
  const config = usePublicConfig();

  if (lead.isLoading) return <div className="muted">{t.app.loading}</div>;
  if (lead.error instanceof ApiError && lead.error.code === "lead_merged") {
    const into = lead.error.detail.into_lead_id;
    if (typeof into === "string") return <Navigate to={`/leads/${into}`} replace />;
  }
  if (lead.error || !lead.data) {
    const code = lead.error instanceof ApiError ? lead.error.code : "unknown";
    return (
      <>
        <div className="breadcrumb">
          <Link to="/leads">{t.lead.breadcrumb}</Link>
        </div>
        <div className="card" role="alert">
          {errorMessage(code)}
        </div>
      </>
    );
  }
  const data = lead.data;
  const name = displayName(data);
  const first = formatDateTime(data.first_inbound_at, timeZone);
  const sub = [
    format(data.source === "leadgen" ? t.lead.firstForm : t.lead.firstContact, { time: first }),
    format(t.lead.page, { name: data.page.name }),
    data.owner ? format(t.lead.owner, { name: data.owner.name }) : t.leads.noOwner,
  ].join(" · ");

  return (
    <>
      <div className="breadcrumb">
        <Link to="/leads">{t.lead.breadcrumb}</Link> <span aria-hidden="true">/</span> {name}
      </div>
      <header className="lead-head">
        <div className="lead-head__who">
          <div className="lead-head__avatar" aria-hidden="true">
            {name.replace(/[^\p{L}\p{N}]/gu, "").charAt(0).toUpperCase() || "K"}
          </div>
          <div>
            <div className="lead-head__title">
              <h1>{name}</h1>
              <span className={`pill pill--${data.status}`} data-testid="lead-status">
                {t.leads.status[data.status]}
              </span>
              {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
            </div>
            <div className="lead-head__sub">{sub}</div>
          </div>
        </div>
        <a className="btn" href={inboxUrl(data.fb_page_id)} target="_blank" rel="noopener noreferrer">
          {t.lead.openInbox} <span aria-hidden="true">↗</span>
        </a>
      </header>

      {data.overdue ? (
        <div className="banner banner--bad" role="status">
          <span>
            <b>
              {format(t.lead.overdueBanner, {
                hours: Math.round((Date.parse(data.result_due_at) - Date.parse(data.first_inbound_at)) / 3_600_000),
              })}
            </b>{" "}
            {t.lead.overdueBody}
          </span>
        </div>
      ) : null}

      <div className="lead-layout">
        <Timeline lead={data} timeZone={timeZone} />
        <aside>
          {data.permissions.can_update ? (
            <ResultPanel key={data.id} lead={data} timeZone={timeZone} />
          ) : (
            <section className="card note">{t.lead.result.readOnly}</section>
          )}
          {data.permissions.can_remind ? <RemindPanel lead={data} /> : null}
          <SourcePanel lead={data} />
        </aside>
      </div>
    </>
  );
}
