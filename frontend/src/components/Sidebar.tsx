import { Link, NavLink, useNavigate } from "react-router-dom";

import { useLeadSummary } from "../api/leads";
import type { Me } from "../api/types";
import { visibleNav, type NavItem } from "../app/nav";
import { useLogout } from "../auth/useAuth";
import { format, t } from "../i18n";
import { Brand } from "./Brand";
import { Icon } from "./Icon";

/** Lọc sẵn của số đỏ: cùng phạm vi "tất cả thời gian" nên số khớp thẻ "Quá 48 giờ" (decisions.md mục M). */
export const OVERDUE_LINK = "/leads?chip=overdue&period=all";

/** Số khách quá 48 giờ chưa có kết quả, mọi thời điểm, trong phạm vi người đang xem (theo thiết kế). */
function OverdueCount() {
  const summary = useLeadSummary({ period: "all" });
  const count = summary.data?.overdue ?? 0;
  if (!count) return null;
  const label = format(t.nav.overdueBadge, { n: count });
  return (
    <Link to={OVERDUE_LINK} className="nav-count" data-testid="nav-overdue" title={label} aria-label={label}>
      {count}
    </Link>
  );
}

function NavEntry({ item }: { item: NavItem }) {
  const label = t.nav[item.key];
  if (item.later) {
    return (
      <span className="nav-link nav-link--disabled" aria-disabled="true" title={label}>
        <Icon name={item.icon} />
        <span className="nav-label">{label}</span>
        <span className="nav-tag">{t.app.later}</span>
      </span>
    );
  }
  // Số đỏ là link riêng (không lồng trong link menu) để mở danh sách đã lọc sẵn.
  return (
    <div className="nav-item">
      <NavLink to={item.path} className="nav-link" title={label}>
        <Icon name={item.icon} />
        <span className="nav-label">{label}</span>
      </NavLink>
      {item.key === "leads" ? <OverdueCount /> : null}
    </div>
  );
}

/** Menu trái dùng chung cho mọi màn hình máy tính (theo thiết kế). */
export function Sidebar({ me }: { me: Me }) {
  const items = visibleNav(me.permissions);
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <nav className="sidebar" aria-label={t.nav.mainLabel}>
      <Brand />
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
