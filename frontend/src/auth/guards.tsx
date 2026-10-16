import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import type { Me } from "../api/types";
import { t } from "../i18n";
import { useMe } from "./useAuth";

function Loading() {
  return (
    <div className="center-screen muted" role="status">
      {t.app.loading}
    </div>
  );
}

/**
 * Chỉ hiện nội dung khi đã đăng nhập. Ẩn/hiện ở đây chỉ để tiện dùng:
 * quyền thật được kiểm tra ở backend cho mọi API.
 */
export function RequireAuth({
  children,
  allowPasswordChange = false,
}: {
  children: (me: Me) => ReactNode;
  allowPasswordChange?: boolean;
}) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <Loading />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (me.data.must_change_password && !allowPasswordChange) {
    return <Navigate to="/change-password" replace />;
  }
  return <>{children(me.data)}</>;
}
