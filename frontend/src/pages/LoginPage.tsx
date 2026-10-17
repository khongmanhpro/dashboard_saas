import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { homePath } from "../app/nav";
import { useLogin, useMe } from "../auth/useAuth";
import { Brand } from "../components/Brand";
import { errorMessage, t } from "../i18n";

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (me.data) return <Navigate to={homePath(me.data.permissions)} replace />;

  const from = (location.state as { from?: string } | null)?.from;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await login.mutateAsync({ email, password });
      if (result.must_change_password) navigate("/change-password", { replace: true });
      else navigate(from && from !== "/login" ? from : homePath(result.permissions), { replace: true });
    } catch {
      // Lỗi hiển thị qua login.error bên dưới.
    }
  }

  const error = login.error instanceof ApiError ? errorMessage(login.error.code, login.error.detail) : null;

  return (
    <main className="auth-page">
      <div className="card auth-card">
        <Brand />
        <h1>{t.login.title}</h1>
        <form className="auth-form" onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">{t.login.email}</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">{t.login.password}</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error ? (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          ) : null}
          <button type="submit" className="btn btn--primary btn--block" disabled={login.isPending}>
            {login.isPending ? t.login.submitting : t.login.submit}
          </button>
        </form>
      </div>
    </main>
  );
}
