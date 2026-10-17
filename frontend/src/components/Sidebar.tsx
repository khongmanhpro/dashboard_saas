import { NavLink, useNavigate } from "react-router-dom";

import { useLeadSummary } from "../api/leads";
import type { Me } from "../api/types";
import { visibleNav, type NavItem } from "../app/nav";
import { useLogout } from "../auth/useAuth";
import { t } from "../i18n";
import { Icon } from "./Icon";

/** Số khách quá 48 giờ chưa có kết quả, trong phạm vi người đang xem (theo thiết kế). */
function OverdueCount() {
  const summary = useLeadSummary({ period: "all" });
  const count = summary.data?.overdue ?? 0;
  if (!count) return null;
  return (
    <span className="nav-count" data-testid="nav-overdue">
      {count}
    </span>
  );
}

function NavEntry({ item }: { item: NavItem }) {
  if (item.later) {
    return (
      <span className="nav-link nav-link--disabled" aria-disabled="true">
        <Icon name={item.icon} />
        {t.nav[item.key]}
        <span className="nav-tag">{t.app.later}</span>
      </span>
    );
  }
  return (
    <NavLink to={item.path} className="nav-link">
      <Icon name={item.icon} />
      {t.nav[item.key]}
      {item.key === "leads" ? <OverdueCount /> : null}
    </NavLink>
  );
}

/** Menu trái dùng chung cho mọi màn hình máy tính (theo thiết kế). */
export function Sidebar({ me }: { me: Me }) {
  const items = visibleNav(me.permissions);
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <nav className="sidebar" aria-label={t.nav.mainLabel}>
      <div className="brand">
        <div className="brand__logo" aria-hidden="true">
          {t.app.logoLetter}
        </div>
        <div className="brand__name">{t.app.name}</div>
      </div>
      {(["main", "admin"] as const).map((group) => {
        const groupItems = items.filter((i) => i.group === group);
        if (groupItems.length === 0) return null;
        return (
          <div className="nav-group" key={group}>
            {groupItems.map((item) => (
              <NavEntry key={item.key} item={item} />
            ))}
          </div>
        );
      })}
      <div className="account">
        <div>
          <div className="account__name">{me.user.full_name}</div>
          <div className="account__role" data-testid="current-role">
            {t.roles[me.member.role]}
          </div>
        </div>
        <button
          type="button"
          className="btn"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login", { replace: true }) })}
        >
          {t.account.logout}
        </button>
      </div>
    </nav>
  );
}
