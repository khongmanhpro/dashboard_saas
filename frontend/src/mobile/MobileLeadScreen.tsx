import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useLead } from "../api/leads";
import type { Me } from "../api/types";
import { errorMessage, t } from "../i18n";
import { displayName } from "../leads/format";
import { inboxUrl, ResultPanel, SourcePanel, Timeline } from "../pages/leads/LeadDetailPage";

export function MobileLeadScreen({ me }: { me: Me }) {
  const { id = "" } = useParams();
  const lead = useLead(id);
  const timeZone = me.workspace.timezone;
  if (lead.isLoading) return <div className="muted m-pad">{t.app.loading}</div>;
  if (!lead.data) {
    return (
      <div className="m-pad">
        <Link to="/m">{t.mobile.back}</Link>
        <div className="card" role="alert">
          {errorMessage(lead.error instanceof ApiError ? lead.error.code : "unknown")}
        </div>
      </div>
    );
  }
  const data = lead.data;
  return (
    <div className="m-pad m-stack">
      <Link to="/m">{t.mobile.back}</Link>
      <div className="lead-head__title">
        <h1 className="m-title">{displayName(data)}</h1>
        <span className={`pill pill--${data.status}`} data-testid="lead-status">
          {t.leads.status[data.status]}
        </span>
      </div>
      <a className="btn btn--block" href={inboxUrl(data.fb_page_id)} target="_blank" rel="noopener noreferrer">
        {t.mobile.replyMessenger} <span aria-hidden="true">↗</span>
      </a>
      {data.permissions.can_update ? <ResultPanel key={data.id} lead={data} timeZone={timeZone} /> : null}
      <Timeline lead={data} timeZone={timeZone} />
      <SourcePanel lead={data} />
    </div>
  );
}
