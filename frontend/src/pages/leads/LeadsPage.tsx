import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import {
  LEAD_STATUSES,
  useFilterOptions,
  useLeadList,
  useLeadSummary,
  type Chip,
  type LeadCard,
  type LeadFilters,
  type LeadStatus,
  type Period,
  type SourceFilter,
} from "../../api/leads";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { cardTimer, displayName, initials, sourceLabel } from "../../leads/format";

type View = "board" | "table";
const VIEW_KEY = "leads.view";
const BOARD_PAGE = 10;
const TABLE_PAGE = 30;

const CHIPS: { key: Chip | undefined; tone: string }[] = [
  { key: undefined, tone: "" },
  { key: "unreplied", tone: "chip--bad" },
  { key: "overdue", tone: "chip--bad" },
  { key: "phone_not_called", tone: "chip--warn" },
  { key: "new_today", tone: "chip--info" },
];

function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "board";
  } catch {
    return "board";
  }
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

function PhoneTags({ lead }: { lead: LeadCard }) {
  return (
    <span className="tags">
      <span className={lead.phone ? "tag tag--good" : "tag"}>{lead.phone ? t.leads.hasPhone : t.leads.noPhone}</span>
      {lead.phone && lead.status !== "won" && lead.status !== "lost" ? (
        <span className={lead.called_at ? "tag tag--info" : "tag tag--warn"}>
          {lead.called_at ? t.leads.called : t.leads.notCalled}
        </span>
      ) : null}
    </span>
  );
}

function LeadCardView({ lead, timeZone, now }: { lead: LeadCard; timeZone: string; now: Date }) {
  const timer = cardTimer(lead, now, timeZone);
  const owner = lead.owner?.name ?? t.leads.noOwner;
  return (
    <Link to={`/leads/${lead.id}`} className="lead-card" data-testid="lead-card">
      <span className="lead-card__top">
        <span className="lead-card__name">{displayName(lead)}</span>
        <span className={timer.hot ? "timer timer--hot" : "timer"}>{timer.text}</span>
      </span>
      <span className="lead-card__meta">{lead.page.name}</span>
      <span className="lead-card__source">{sourceLabel(lead)}</span>
      <span className="lead-card__bottom">
        <PhoneTags lead={lead} />
        <span className="avatar" title={owner} aria-label={owner}>
          {lead.owner ? initials(lead.owner.name) : "–"}
        </span>
      </span>
    </Link>
  );
}

function BoardColumn({
  status,
  filters,
  count,
  timeZone,
  now,
}: {
  status: LeadStatus;
  filters: LeadFilters;
  count: number | undefined;
  timeZone: string;
  now: Date;
}) {
  const list = useLeadList(filters, status, BOARD_PAGE);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const remaining = count === undefined ? 0 : Math.max(0, count - items.length);
  return (
    <section className="board-col" aria-label={t.leads.columns[status]} data-testid={`column-${status}`}>
      <div className="board-col__head">
        <span>
          <span className={`dot dot--${status}`} aria-hidden="true" />
          {t.leads.columns[status]}
        </span>
        <span>{count ?? ""}</span>
      </div>
      {items.map((lead) => (
        <LeadCardView key={lead.id} lead={lead} timeZone={timeZone} now={now} />
      ))}
      {list.hasNextPage ? (
        <button
          type="button"
          className="link-btn"
          disabled={list.isFetchingNextPage}
          onClick={() => void list.fetchNextPage()}
        >
          {t.leads.more} {remaining || ""}
        </button>
      ) : null}
    </section>
  );
}

function LeadTable({ filters, timeZone, now }: { filters: LeadFilters; timeZone: string; now: Date }) {
  const list = useLeadList(filters, undefined, TABLE_PAGE);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">{t.leads.table.customer}</th>
            <th scope="col">{t.leads.table.pageOwner}</th>
            <th scope="col">{t.leads.table.source}</th>
            <th scope="col">{t.leads.table.timer}</th>
            <th scope="col">{t.leads.table.phone}</th>
            <th scope="col">{t.leads.table.status}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((lead) => {
            const timer = cardTimer(lead, now, timeZone);
            return (
              <tr key={lead.id} data-testid="lead-row">
                <td>
                  <Link to={`/leads/${lead.id}`} className="lead-card__name">
                    {displayName(lead)}
                  </Link>
                </td>
                <td>
                  {lead.page.name} · {lead.owner?.name ?? t.leads.noOwner}
                </td>
                <td className="muted">{sourceLabel(lead)}</td>
                <td className={timer.hot ? "timer timer--hot" : "timer"}>{timer.text}</td>
                <td>{lead.phone ?? "—"}</td>
                <td>
                  <span className={`pill pill--${lead.status}`}>{t.leads.status[lead.status]}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!list.isLoading && items.length === 0 ? <div className="card muted">{t.leads.empty}</div> : null}
      {list.hasNextPage ? (
        <button type="button" className="link-btn" onClick={() => void list.fetchNextPage()}>
          {t.leads.more}
        </button>
      ) : null}
    </div>
  );
}

export function LeadsPage() {
  const me = useOutletContext<Me>();
  const timeZone = me.workspace.timezone;
  const [view, setView] = useState<View>(readView);
  const [chip, setChip] = useState<Chip | undefined>();
  const [period, setPeriod] = useState<Period>("7d");
  const [pageId, setPageId] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [source, setSource] = useState<SourceFilter | "">("");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 300);
  const options = useFilterOptions();
  const now = useMemo(() => new Date(), []);

  const filters: LeadFilters = {
    period,
    chip,
    page_id: pageId || undefined,
    owner_id: ownerId || undefined,
    source: source || undefined,
    q: q || undefined,
  };
  const summary = useLeadSummary(filters);

  const chooseView = (next: View) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Trình duyệt chặn localStorage: chỉ không nhớ được kiểu xem.
    }
  };

  const chipCount = (key: Chip | undefined) => {
    const s = summary.data;
    if (!s) return "";
    return key ? s[key] : s.total;
  };

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.leads.title} />
          <div className="page-sub">{t.leads.subtitle}</div>
        </div>
        <div className="segmented" role="group" aria-label={t.leads.viewLabel}>
          <button type="button" aria-pressed={view === "board"} onClick={() => chooseView("board")}>
            {t.leads.viewBoard}
          </button>
          <button type="button" aria-pressed={view === "table"} onClick={() => chooseView("table")}>
            {t.leads.viewTable}
          </button>
        </div>
      </div>

      <div className="chips">
        {CHIPS.map(({ key, tone }) => (
          <button
            key={key ?? "all"}
            type="button"
            className={`chip ${tone}`}
            aria-pressed={chip === key}
            onClick={() => setChip(key)}
          >
            <span>{key ? t.leads.chips[key] : t.leads.chips.all}</span>
            <b>{chipCount(key)}</b>
          </button>
        ))}
      </div>

      <div className="filters" role="search" aria-label={t.leads.filters.label}>
        <label className="filters__search">
          <span className="sr-only">{t.leads.filters.search}</span>
          <input
            type="search"
            value={search}
            placeholder={t.leads.filters.searchPlaceholder}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <label className="select">
          {t.leads.filters.page}
          <select value={pageId} onChange={(e) => setPageId(e.target.value)}>
            <option value="">{t.leads.filters.all}</option>
            {options.data?.pages.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {options.data && options.data.owners.length > 1 ? (
          <label className="select">
            {t.leads.filters.owner}
            <select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
              <option value="">{t.leads.filters.all}</option>
              {options.data.owners.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="select">
          {t.leads.filters.source}
          <select value={source} onChange={(e) => setSource(e.target.value as SourceFilter | "")}>
            <option value="">{t.leads.filters.allSources}</option>
            {(["ad", "organic", "form"] as const).map((s) => (
              <option key={s} value={s}>
                {t.leads.filters.sources[s]}
              </option>
            ))}
          </select>
        </label>
        <label className="select">
          {t.leads.filters.period}
          <select value={period} onChange={(e) => setPeriod(e.target.value as Period)}>
            {(["today", "7d", "30d", "all"] as const).map((p) => (
              <option key={p} value={p}>
                {t.leads.filters.periods[p]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {view === "board" ? (
        <div className="board">
          {LEAD_STATUSES.map((status) => (
            <BoardColumn
              key={status}
              status={status}
              filters={filters}
              count={summary.data?.by_status[status]}
              timeZone={timeZone}
              now={now}
            />
          ))}
        </div>
      ) : (
        <LeadTable filters={filters} timeZone={timeZone} now={now} />
      )}
    </>
  );
}
