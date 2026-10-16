import { Link } from "react-router-dom";

import type { Me } from "../api/types";
import { homePath } from "../app/nav";
import { usePublicConfig } from "../auth/useAuth";
import { t } from "../i18n";

/** Khung ứng dụng điện thoại cho nhân viên (PWA, đường dẫn /m). Nội dung làm ở Bước 5. */
export function MobileShell({ me }: { me: Me }) {
  const config = usePublicConfig();
  const desktop = homePath(me.permissions);
  return (
    <div className="mobile">
      <header className="mobile__header">
        <h1>{t.mobile.title}</h1>
        {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
      </header>
      <div className="mobile__body">
        <p className="muted">{t.mobile.body}</p>
        {desktop !== "/m" ? (
          <Link className="btn" to={desktop}>
            {t.mobile.desktop}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
