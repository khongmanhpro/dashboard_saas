import { Link } from "react-router-dom";

import { t } from "../i18n";

export function NotFoundPage() {
  return (
    <main className="auth-page">
      <div className="card auth-card">
        <h1>{t.notFound.title}</h1>
        <Link to="/">{t.notFound.back}</Link>
      </div>
    </main>
  );
}
