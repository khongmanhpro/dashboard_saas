import { useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";
import { canSee, type NavItem } from "../app/nav";
import { PageHeader } from "../components/PageHeader";
import { format, t } from "../i18n";

/** Chỗ giữ cho các màn hình nghiệp vụ, sẽ thay bằng màn hình thật ở bước tương ứng. */
export function PlaceholderPage({ item }: { item: NavItem }) {
  const me = useOutletContext<Me>();
  if (!canSee(item, me.permissions)) {
    return (
      <>
        <PageHeader title={t.forbidden.title} />
        <div className="card">{t.forbidden.body}</div>
      </>
    );
  }
  return (
    <>
      <PageHeader title={t.nav[item.key]} />
      <div className="card muted">{format(t.placeholder.body, { step: item.step })}</div>
    </>
  );
}
