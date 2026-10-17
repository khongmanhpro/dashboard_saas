import { useNavigate } from "react-router-dom";

import { useMarkRead, useNotifications } from "../api/mobile";
import { t } from "../i18n";
import { formatDuration } from "../leads/format";

export function RemindersScreen() {
  const list = useNotifications();
  const mark = useMarkRead();
  const navigate = useNavigate();
  const now = Date.now();
  return (
    <div className="m-pad m-stack">
      <div className="page-top">
        <h1 className="m-title">{t.mobile.reminders.title}</h1>
        {list.data?.unread ? (
          <button type="button" className="link-btn" onClick={() => mark.mutate("all")}>
            {t.mobile.reminders.readAll}
          </button>
        ) : null}
      </div>
      {list.data?.items.length === 0 ? <div className="m-empty">{t.mobile.reminders.empty}</div> : null}
      {list.data?.items.map((n) => (
        <button
          key={n.id}
          type="button"
          className={n.read_at ? "m-notice" : "m-notice m-notice--unread"}
          data-testid="m-notice"
          onClick={() => {
            if (!n.read_at) mark.mutate(n.id);
            if (n.lead_id) navigate(`/m/leads/${n.lead_id}`);
          }}
        >
          <b>{n.title}</b>
          <span>{n.body}</span>
          <time dateTime={n.created_at}>{formatDuration((now - Date.parse(n.created_at)) / 1000)}</time>
        </button>
      ))}
    </div>
  );
}
