import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";

import { ApiError } from "../../api/client";
import { useBmAction, useBms, usePages, useSetPageOwner, type Bm, type PageRow } from "../../api/bms";
import type { Me } from "../../api/types";
import { PageHeader } from "../../components/PageHeader";
import { errorMessage, format, t } from "../../i18n";
import { formatDateTime } from "../../leads/format";
import { AddBmPanel } from "./AddBmPanel";

const STATUS_PILL: Record<Bm["status"], string> = {
  active: "pill pill--won",
  missing_permissions: "pill pill--warn",
  disconnected: "pill pill--new",
};

function BmRow({ bm, canConnect, timeZone, onRotate }: { bm: Bm; canConnect: boolean; timeZone: string; onRotate: () => void }) {
  const action = useBmAction();
  const verification =
    bm.verification_status && bm.verification_status in t.bm.verification
      ? t.bm.verification[bm.verification_status as keyof typeof t.bm.verification]
      : bm.verification_status;
  let note: string | null = null;
  if (bm.missing_scopes.length) note = format(t.bm.missing, { scopes: bm.missing_scopes.join(", ") });
  if (bm.status_detail && bm.status_detail in t.bm.statusDetail) {
    note = t.bm.statusDetail[bm.status_detail as keyof typeof t.bm.statusDetail];
  }
  return (
    <tr data-testid="bm-row">
      <td>
        <b>{bm.name}</b>
        <div className="muted">
          {format(t.bm.idLine, { id: bm.fb_business_id })}
          {verification ? ` · ${verification}` : ""}
        </div>
      </td>
      <td>
        {bm.system_user_name ?? "—"}
        <div className="muted">
          {bm.token_last4 ? (bm.is_mock ? t.bm.mockToken : format(t.bm.token, { last4: bm.token_last4 })) : ""}
        </div>
      </td>
      <td>
        <span className={STATUS_PILL[bm.status]}>{t.bm.status[bm.status]}</span>
        {note ? <div className="muted bm-note">{note}</div> : null}
      </td>
      <td>{bm.page_count}</td>
      <td>{bm.ad_account_count}</td>
      <td>{bm.last_checked_at ? formatDateTime(bm.last_checked_at, timeZone) : t.bm.never}</td>
      <td>
        {canConnect ? (
          <div className="row-actions">
            <button type="button" className="btn" onClick={onRotate}>
              {t.bm.actions.rotate}
            </button>
            {bm.token_last4 ? (
              <>
                <button
                  type="button"
                  className="btn"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ id: bm.id, action: "check" })}
                >
                  {t.bm.actions.recheck}
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={action.isPending}
                  onClick={() => {
                    if (window.confirm(t.bm.actions.confirmDisconnect)) action.mutate({ id: bm.id, action: "disconnect" });
                  }}
                >
                  {t.bm.actions.disconnect}
                </button>
              </>
            ) : null}
          </div>
        ) : null}
        {action.error instanceof ApiError ? <div className="alert alert--error">{errorMessage(action.error.code)}</div> : null}
      </td>
    </tr>
  );
}

function OwnerSelect({ page, candidates, canAssign }: { page: PageRow; candidates: { id: string; name: string }[]; canAssign: boolean }) {
  const setOwner = useSetPageOwner();
  if (!page.is_tracked) {
    return <span className="muted">{page.untracked_reason ? t.bm.untracked[page.untracked_reason] : "—"}</span>;
  }
  if (!canAssign) return <span>{page.owner?.name ?? t.leads.noOwner}</span>;
  const options = page.owner && !candidates.some((c) => c.id === page.owner?.id) ? [page.owner, ...candidates] : candidates;
  return (
    <>
      <select
        className="form-select"
        aria-label={format(t.bm.ownerLabel, { page: page.name })}
        value={page.owner?.id ?? ""}
        disabled={setOwner.isPending}
        onChange={(e) => setOwner.mutate({ pageId: page.id, memberId: e.target.value || null })}
      >
        <option value="" disabled={!page.owner}>
          {page.owner ? t.bm.noOwner : t.bm.chooseOwner}
        </option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      {setOwner.error instanceof ApiError ? (
        <div className="alert alert--error" role="alert">
          {errorMessage(setOwner.error.code)}
        </div>
      ) : null}
    </>
  );
}

export function BmPage() {
  const me = useOutletContext<Me>();
  const timeZone = me.workspace.timezone;
  const overview = useBms();
  const pages = usePages();
  const [panel, setPanel] = useState<{ rotate: Bm | null } | null>(null);
  const [showAll, setShowAll] = useState(false);
  const canAssign = "page.assign" in me.permissions;
  const canImport = "member.manage" in me.permissions;
  const data = overview.data;
  const rows = (pages.data?.pages ?? []).filter((p) => showAll || (p.is_tracked && !p.owner));

  return (
    <>
      <div className="page-top">
        <div>
          <PageHeader title={t.bm.title} />
          <div className="page-sub">{t.bm.subtitle}</div>
        </div>
        {data?.can_connect ? (
          <button type="button" className="btn btn--primary" onClick={() => setPanel({ rotate: null })}>
            {t.bm.add}
          </button>
        ) : null}
      </div>

      {data ? (
        <section className="kpis">
          {[
            [t.bm.kpis.bms, data.bms.length],
            [t.bm.kpis.pages, data.tracked_pages],
            [t.bm.kpis.unassigned, data.unassigned_pages],
            [t.bm.kpis.ads, data.ad_accounts],
          ].map(([label, value]) => (
            <div key={String(label)} className="kpi">
              <div className="kpi__label">{label}</div>
              <div className="kpi__value" data-testid={`kpi-${label}`}>
                {value}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <div className="bm-layout">
        <div className="m-stack bm-main">
          <section className="card" aria-labelledby="bm-list">
            <div className="section-head section-head--row">
              <h2 id="bm-list">{t.bm.listTitle}</h2>
              <span>{t.bm.listHint}</span>
            </div>
            <div className="table-wrap table-wrap--plain">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t.bm.table.bm}</th>
                    <th scope="col">{t.bm.table.systemUser}</th>
                    <th scope="col">{t.bm.table.status}</th>
                    <th scope="col">{t.bm.table.pages}</th>
                    <th scope="col">{t.bm.table.ads}</th>
                    <th scope="col">{t.bm.table.checked}</th>
                    <th scope="col">
                      <span className="sr-only">{t.bm.table.actions}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data?.bms.map((bm) => (
                    <BmRow
                      key={bm.id}
                      bm={bm}
                      canConnect={data.can_connect}
                      timeZone={timeZone}
                      onRotate={() => setPanel({ rotate: bm })}
                    />
                  ))}
                </tbody>
              </table>
              {data && data.bms.length === 0 ? <p className="note">{t.bm.empty}</p> : null}
            </div>
          </section>

          <section className="card" aria-labelledby="bm-pages">
            <div className="section-head section-head--row">
              <div>
                <h2 id="bm-pages">
                  {showAll ? t.bm.pagesAllTitle : format(t.bm.pagesTitle, { n: data?.unassigned_pages ?? 0 })}
                </h2>
                <span>{t.bm.pagesHint}</span>
              </div>
              <div className="row-actions">
                <div className="segmented" role="group">
                  <button type="button" aria-pressed={!showAll} onClick={() => setShowAll(false)}>
                    {t.bm.viewUnassigned}
                  </button>
                  <button type="button" aria-pressed={showAll} onClick={() => setShowAll(true)}>
                    {t.bm.viewAll}
                  </button>
                </div>
                {canImport ? <Link to="/staff?import=1">{t.bm.excelLink}</Link> : null}
              </div>
            </div>
            <div className="table-wrap table-wrap--plain">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t.bm.pageTable.page}</th>
                    <th scope="col">{t.bm.pageTable.bm}</th>
                    <th scope="col">{t.bm.pageTable.leads}</th>
                    <th scope="col">{t.bm.pageTable.owner}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((page) => (
                    <tr key={page.id} data-testid="page-row">
                      <td>
                        {page.name}
                        {page.is_new ? <span className="tag tag--sample">{t.bm.newTag}</span> : null}
                        {page.is_tracked && !page.webhook_subscribed ? <div className="muted">{t.bm.noWebhook}</div> : null}
                      </td>
                      <td className="muted">{page.business_manager}</td>
                      <td>{page.leads_7d}</td>
                      <td>
                        <OwnerSelect page={page} candidates={pages.data?.candidates ?? []} canAssign={canAssign} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {pages.data && rows.length === 0 ? <p className="note">{t.bm.allAssigned}</p> : null}
            </div>
          </section>
        </div>
        {panel ? <AddBmPanel key={panel.rotate?.id ?? "new"} rotate={panel.rotate} onClose={() => setPanel(null)} /> : null}
      </div>
    </>
  );
}
