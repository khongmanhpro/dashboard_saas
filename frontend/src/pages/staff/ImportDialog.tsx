import { useState } from "react";

import { ApiError } from "../../api/client";
import { downloadBase64, previewImport, useApplyImport, type ImportPreview } from "../../api/bms";
import { errorMessage, format, t } from "../../i18n";

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function rowError(code: string): string {
  return code in t.imports.rowErrors ? t.imports.rowErrors[code as keyof typeof t.imports.rowErrors] : code;
}

/** Nhập nhân viên từ Excel (Staff.dc.html, hộp thoại 3 bước). */
export function ImportDialog({ onClose }: { onClose: () => void }) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const apply = useApplyImport();

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setReading(true);
    setReadError(null);
    setPreview(null);
    apply.reset();
    try {
      setPreview(await previewImport(file));
    } catch (error) {
      setReadError(errorMessage(error instanceof ApiError ? error.code : "unknown"));
    } finally {
      setReading(false);
    }
  };

  const result = apply.data;
  return (
    <div className="dialog-backdrop">
      <div className="dialog card" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <div className="section-head section-head--row">
          <div>
            <h2 id="import-title">{t.imports.title}</h2>
            <span>{t.imports.hint}</span>
          </div>
          <button type="button" className="link-btn" aria-label={t.imports.close} onClick={onClose}>
            ×
          </button>
        </div>
        <div className="import-steps">
          <div>
            <b>{t.imports.step1}</b>
            <span className="note">{t.imports.columns}</span>
            <a href="/api/imports/members/template" download>
              {t.imports.template}
            </a>
          </div>
          <label className="import-drop">
            <b>{t.imports.step2}</b>
            <span className="note">
              {reading
                ? t.imports.reading
                : preview
                  ? format(t.imports.fileInfo, { name: preview.file_name, n: preview.rows_total })
                  : t.imports.choose}
            </span>
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              aria-label={t.imports.choose}
              onChange={(e) => void choose(e.target.files?.[0])}
            />
          </label>
        </div>
        {readError ? (
          <div className="alert alert--error" role="alert">
            {readError}
          </div>
        ) : null}
        {preview ? (
          <>
            <div className="section-head section-head--row">
              <b>{t.imports.step3}</b>
              <span>
                <span className="good-text">{format(t.imports.okCount, { n: preview.rows_ok })}</span> ·{" "}
                <span className="bad-text">{format(t.imports.failCount, { n: preview.rows_failed })}</span>
              </span>
            </div>
            <div className="table-wrap table-wrap--plain import-table">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t.imports.table.row}</th>
                    <th scope="col">{t.imports.table.name}</th>
                    <th scope="col">{t.imports.table.team}</th>
                    <th scope="col">{t.imports.table.page}</th>
                    <th scope="col">{t.imports.table.check}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={row.row} data-testid="import-row">
                      <td>{row.row}</td>
                      <td>
                        {row.full_name || "—"}
                        <div className="muted">{row.email}</div>
                      </td>
                      <td>{row.team ?? "—"}</td>
                      <td>{row.page ?? "—"}</td>
                      <td className={row.errors.length ? "bad-text" : "good-text"}>
                        {row.errors.length ? `✕ ${row.errors.map(rowError).join("; ")}` : t.imports.valid[row.action ?? "create"]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
        {result ? (
          <div className="alert alert--ok" role="status">
            {format(t.imports.done, { created: result.created, updated: result.updated, skipped: result.skipped })}
          </div>
        ) : null}
        {result?.credentials_file ? (
          <div className="m-stack">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => downloadBase64(result.credentials_file ?? "", "mat-khau-tam.xlsx", XLSX)}
            >
              {t.imports.credentials}
            </button>
            <p className="note">{t.imports.credentialsNote}</p>
          </div>
        ) : null}
        {apply.error instanceof ApiError ? (
          <div className="alert alert--error" role="alert">
            {errorMessage(apply.error.code)}
          </div>
        ) : null}
        <div className="bm-panel__actions">
          <button type="button" className="btn" onClick={onClose}>
            {result ? t.imports.close : t.imports.cancel}
          </button>
          {preview && !result ? (
            <button
              type="button"
              className="btn btn--primary"
              disabled={preview.rows_ok === 0 || apply.isPending}
              onClick={() => apply.mutate(preview.id)}
            >
              {apply.isPending ? t.imports.applying : format(t.imports.apply, { ok: preview.rows_ok, failed: preview.rows_failed })}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
