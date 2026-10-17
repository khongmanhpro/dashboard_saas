import { NavLink, Route, Routes } from "react-router-dom";

import { useMobileHome } from "../api/mobile";
import type { Me } from "../api/types";
import { t } from "../i18n";
import { AccountScreen } from "./AccountScreen";
import { MobileLeadScreen } from "./MobileLeadScreen";
import { MyLeadsScreen } from "./MyLeadsScreen";
import { MyScoreScreen } from "./MyScoreScreen";
import { RemindersScreen } from "./RemindersScreen";

function BottomNav() {
  const home = useMobileHome();
  const unread = home.data?.unread ?? 0;
  return (
    <nav className="m-nav" aria-label={t.mobile.nav.label}>
      <NavLink to="/m" end>
        {t.mobile.nav.leads}
      </NavLink>
      <NavLink to="/m/score">{t.mobile.nav.score}</NavLink>
      <NavLink to="/m/reminders">
        {t.mobile.nav.reminders}
        {unread ? (
          <span className="nav-count" data-testid="m-unread">
            {unread}
          </span>
        ) : null}
      </NavLink>
      <NavLink to="/m/account">{t.mobile.nav.account}</NavLink>
    </nav>
  );
}

/** Ứng dụng điện thoại cho nhân viên (PWA, đường dẫn /m). Chỉ hiện khách của chính mình. */
export function MobileShell({ me }: { me: Me }) {
  return (
    <div className="mobile">
      <div className="m-content">
        <Routes>
          <Route index element={<MyLeadsScreen me={me} />} />
          <Route path="leads/:id" element={<MobileLeadScreen me={me} />} />
          <Route path="score" element={<MyScoreScreen me={me} />} />
          <Route path="reminders" element={<RemindersScreen />} />
          <Route path="account" element={<AccountScreen me={me} />} />
        </Routes>
      </div>
      <BottomNav />
    </div>
  );
}
