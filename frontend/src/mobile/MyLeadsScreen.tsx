import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { LOST_REASONS, useSetCalled, useSetResult, type LostReason } from "../api/leads";
import { MOBILE_TABS, useMobileHome, useMobileLeads, type MobileLead, type MobileTab } from "../api/mobile";
import type { Me } from "../api/types";
import { usePublicConfig } from "../auth/useAuth";
import { errorMessage, format, t } from "../i18n";
import { cardTimer, displayName, formatDuration, formatVnd, groupThousands, parseVndInput, sourceLabel, zonedLocalToIso } from "../leads/format";
import { inboxUrl } from "../pages/leads/LeadDetailPage";
import { formatPercent, formatScore } from "../staff/format";
import { quickCallbackTimes } from "./callbackOptions";

type SheetMode = "won" | "callback" | "lost";

function Header({ me }: { me: Me }) {
  const home = useMobileHome();
  const config = usePublicConfig();
  const data = home.data;
  const score = data?.score;
  let hint: string = t.mobile.noScore;
  if (score?.insufficient_data) hint = format(t.mobile.insufficient, { min: score.min_leads, n: score.lead_count });
  else if (score?.next_tier && score.points_to_next) {
    hint = format(t.mobile.toNext, { n: formatScore(score.points_to_next), tier: score.next_tier });
  } else if (score?.total) hint = t.mobile.topTier;
  return (
    <header className="m-hero">
      <div className="m-hero__top">
        <div>
          <div className="m-hero__page">
            {data?.pages.length ? format(t.mobile.pageLabel, { name: data.pages.join(", ") }) : t.mobile.noPage}
          </div>
          <div className="m-hero__hello">{format(t.mobile.hello, { name: data?.first_name || me.user.full_name })}</div>
        </div>
        {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
      </div>
      <div className="m-hero__score">
        {score?.total ? (
          <div className="m-hero__points">
            <b data-testid="m-score">{formatScore(score.total)}</b>
            <span>{format(t.mobile.tier, { tier: score.tier ?? "" })}</span>
          </div>
        ) : null}
        <div className="m-hero__rank">
          {score?.rank ? (
            <span>
              <b>{format(t.mobile.rank, { rank: score.rank, total: score.ranked_count })}</b>
              {score.rank_change ? (
                <span className={score.rank_change > 0 ? "delta delta--up" : "delta delta--down"}>
                  {" · "}
                  {format(score.rank_change > 0 ? t.mobile.rankUp : t.mobile.rankDown, { n: Math.abs(score.rank_change) })}
                </span>
              ) : null}
            </span>
          ) : null}
          <span>
            {hint}
            {data?.phone_not_called ? ` ${format(t.mobile.notCalled, { n: data.phone_not_called })}` : ""}
          </span>
        </div>
      </div>
      {data?.stats ? (
        <div className="m-hero__stats">
          <div>
            <span>{t.mobile.stats.reply}</span>
            <b>{data.stats.median_response_seconds === null ? "—" : formatDuration(data.stats.median_response_seconds)}</b>
          </div>
          <div>
            <span>{t.mobile.stats.phone}</span>
            <b>{formatPercent(data.stats.phone_rate)}</b>
          </div>
          <div>
            <span>{t.mobile.stats.close}</span>
            <b>{formatPercent(data.stats.close_rate)}</b>
          </div>
        </div>
      ) : null}
    </header>
  );
}

function Sheet({
  lead,
  mode,
  timeZone,
  onClose,
}: {
  lead: MobileLead;
  mode: SheetMode;
  timeZone: string;
  onClose: () => void;
}) {
  const save = useSetResult(lead.id);
  const [value, setValue] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const [custom, setCustom] = useState("");
  const [note, setNote] = useState("");
  const quick = quickCallbackTimes(new Date(), timeZone);

  let body: Parameters<typeof save.mutate>[0] | null = null;
  if (mode === "won") {
    const v = parseVndInput(value);
    body = v ? { status: "won", won_value_vnd: v } : null;
  } else if (mode === "callback") {
    const iso = choice === "other" ? zonedLocalToIso(custom, timeZone) : quick.find((q) => q.key === choice)?.iso;
    body = iso ? { status: "callback", callback_at: iso } : null;
  } else if (choice) {
    const reason = choice as LostReason;
    body = reason === "other" && !note.trim() ? null : { status: "lost", lost_reason: reason, note: note.trim() || undefined };
  }

  return (
    <div className="m-sheet">
      <button type="button" className="m-sheet__backdrop" aria-label={t.mobile.sheet.close} onClick={onClose} />
      <div className="m-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <span className="m-sheet__grip" aria-hidden="true" />
        <h2 id="sheet-title">{t.mobile.sheet[mode]}</h2>
        <p className="note">{displayName(lead)}</p>
        {mode === "won" ? (
          <div className="field">
            <label htmlFor="m-won">{t.lead.result.wonValue}</label>
            <span className="money-input">
              <input
                id="m-won"
                inputMode="numeric"
                autoFocus
                value={value}
                onChange={(e) => {
                  const v = parseVndInput(e.target.value);
                  setValue(v === null ? "" : groupThousands(v));
                }}
              />
              <span>{t.lead.result.currency}</span>
            </span>
          </div>
        ) : null}
        {mode === "callback" ? (
          <div className="m-options">
            {quick.map((q) => (
              <button key={q.key} type="button" aria-pressed={choice === q.key} onClick={() => setChoice(q.key)}>
                {q.label}
              </button>
            ))}
            <button type="button" aria-pressed={choice === "other"} onClick={() => setChoice("other")}>
              {t.mobile.sheet.otherTime}
            </button>
            {choice === "other" ? (
              <input
                type="datetime-local"
                aria-label={t.lead.result.callbackAt}
                value={custom}
                onChange={(e) => setCustom(e.target.value)}
              />
            ) : null}
          </div>
        ) : null}
        {mode === "lost" ? (
          <div className="m-options">
            {LOST_REASONS.map((reason) => (
              <button key={reason} type="button" aria-pressed={choice === reason} onClick={() => setChoice(reason)}>
                {t.leads.lostReasons[reason]}
              </button>
            ))}
            {choice === "other" ? (
              <textarea
                rows={2}
                aria-label={t.lead.result.note}
                placeholder={t.lead.result.noteRequired}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            ) : null}
          </div>
        ) : null}
        {save.error ? (
          <div className="alert alert--error" role="alert">
            {save.error instanceof ApiError ? errorMessage(save.error.code) : t.errors.unknown}
          </div>
        ) : null}
        <button
          type="button"
          className="btn btn--primary btn--block"
          disabled={!body || save.isPending}
          onClick={() => body && save.mutate(body, { onSuccess: onClose })}
        >
          {save.isPending ? t.mobile.sheet.saving : t.mobile.sheet.save}
        </button>
      </div>
    </div>
  );
}

function LeadCardItem({ lead, timeZone, onAction }: { lead: MobileLead; timeZone: string; onAction: (mode: SheetMode) => void }) {
  const setCalled = useSetCalled(lead.id);
  const timer = cardTimer(lead, new Date(), timeZone);
  const done = lead.status === "won" || lead.status === "lost";
  const snippet = lead.snippet === null ? (lead.source === "leadgen" ? t.mobile.noSnippet : "") : lead.snippet || t.mobile.attachment;
  let phoneTag = <span className="tag">{t.leads.noPhone}</span>;
  if (lead.phone) {
    phoneTag = lead.called_at ? (
      <span className="tag tag--info">{t.leads.called}</span>
    ) : (
      <span className="tag tag--warn">{t.mobile.phoneNotCalled}</span>
    );
  }
  return (
    <article className="m-card" data-testid="m-card">
      <div className="m-card__top">
        <Link to={`/m/leads/${lead.id}`} className="m-card__name">
          {displayName(lead)}
        </Link>
        <span className={timer.hot ? "timer timer--hot" : "timer"}>{timer.text}</span>
      </div>
      {snippet ? <p className="m-card__snippet">{snippet}</p> : null}
      <div className="m-card__meta">
        {phoneTag}
        <span className="muted">{sourceLabel(lead)}</span>
      </div>
      {lead.waiting_business_seconds !== null ? (
        <a className="m-card__reply" href={inboxUrl(lead.fb_page_id)} target="_blank" rel="noopener noreferrer">
          {t.mobile.replyMessenger} <span aria-hidden="true">↗</span>
        </a>
      ) : null}
      {done ? (
        <div className={lead.status === "won" ? "m-card__done m-card__done--won" : "m-card__done"}>
          {lead.status === "won"
            ? `${t.mobile.done.won}${lead.won_value_vnd ? ` · ${formatVnd(lead.won_value_vnd)}` : ""}`
            : `${t.mobile.done.lost}${lead.lost_reason ? ` · ${t.leads.lostReasons[lead.lost_reason]}` : ""}`}
        </div>
      ) : (
        <div className="m-card__actions">
          {lead.phone && !lead.phone_masked ? (
            <a
              className={lead.called_at ? "m-action m-action--done" : "m-action m-action--call"}
              href={`tel:${lead.phone}`}
              onClick={() => {
                if (!lead.called_at) setCalled.mutate(true);
              }}
            >
              {lead.called_at ? t.mobile.actions.called : t.mobile.actions.call}
            </a>
          ) : null}
          <button type="button" className="m-action" onClick={() => onAction("won")}>
            {t.mobile.actions.won}
          </button>
          <button type="button" className="m-action" onClick={() => onAction("callback")}>
            {t.mobile.actions.callback}
          </button>
          <button type="button" className="m-action" onClick={() => onAction("lost")}>
            {t.mobile.actions.lost}
          </button>
        </div>
      )}
    </article>
  );
}

export function MyLeadsScreen({ me }: { me: Me }) {
  const timeZone = me.workspace.timezone;
  const [tab, setTab] = useState<MobileTab>("todo");
  const [sheet, setSheet] = useState<{ lead: MobileLead; mode: SheetMode } | null>(null);
  const home = useMobileHome();
  const leads = useMobileLeads(tab);
  return (
    <>
      <Header me={me} />
      <div className="m-tabs" role="tablist" aria-label={t.mobile.tabsLabel}>
        {MOBILE_TABS.map((key) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
            {t.mobile.tabs[key]}
            <span>{home.data?.tabs[key] ?? ""}</span>
          </button>
        ))}
      </div>
      <div className="m-list">
        {leads.data?.map((lead) => (
          <LeadCardItem key={lead.id} lead={lead} timeZone={timeZone} onAction={(mode) => setSheet({ lead, mode })} />
        ))}
        {leads.data && leads.data.length === 0 ? <div className="m-empty">{t.mobile.empty[tab]}</div> : null}
      </div>
      {sheet ? <Sheet lead={sheet.lead} mode={sheet.mode} timeZone={timeZone} onClose={() => setSheet(null)} /> : null}
      {home.error instanceof ApiError ? <div className="alert alert--error">{errorMessage(home.error.code)}</div> : null}
    </>
  );
}

