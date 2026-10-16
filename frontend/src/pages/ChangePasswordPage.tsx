import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import type { Me } from "../api/types";
import { homePath } from "../app/nav";
import { useChangePassword } from "../auth/useAuth";
import { errorMessage, t } from "../i18n";

export function ChangePasswordPage({ me }: { me: Me }) {
  const change = useChangePassword();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [mismatch, setMismatch] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    try {
      await change.mutateAsync({ current_password: current, new_password: next });
      navigate(homePath(me.permissions), { replace: true });
    } catch {
      // Lỗi hiển thị bên dưới.
    }
  }

  const error = mismatch
    ? t.changePassword.mismatch
    : change.error instanceof ApiError
      ? errorMessage(change.error.code, change.error.detail)
      : null;

  return (
    <main className="auth-page">
      <div className="card auth-card">
        <h1>{t.changePassword.title}</h1>
        {me.must_change_password ? <p className="muted">{t.changePassword.firstLogin}</p> : null}
        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="current">{t.changePassword.current}</label>
            <input
              id="current"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="next">{t.changePassword.next}</label>
            <input
              id="next"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              aria-describedby="next-hint"
            />
            <span id="next-hint" className="field__hint">
              {t.changePassword.hint}
            </span>
          </div>
          <div className="field">
            <label htmlFor="confirm">{t.changePassword.confirm}</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          {error ? (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          ) : null}
          <button type="submit" className="btn btn--primary btn--block" disabled={change.isPending}>
            {t.changePassword.submit}
          </button>
        </form>
      </div>
    </main>
  );
}
