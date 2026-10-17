import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { JSX, ReactNode } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";
import { RequireAuth } from "../auth/guards";
import { Sidebar } from "../components/Sidebar";
import { MobileShell } from "../mobile/MobileShell";
import { ChangePasswordPage } from "../pages/ChangePasswordPage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { BmPage } from "../pages/bm/BmPage";
import { LeadDetailPage } from "../pages/leads/LeadDetailPage";
import { LeadsPage } from "../pages/leads/LeadsPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { SettingsPage } from "../pages/settings/SettingsPage";
import { StaffDetailPage } from "../pages/staff/StaffDetailPage";
import { StaffPage } from "../pages/staff/StaffPage";
import { canSee, homePath, NAV, type NavItem } from "./nav";

/** Màn hình đã làm xong theo từng mục menu. Mục chưa làm hiện PlaceholderPage. */
const SCREENS: Partial<Record<NavItem["key"], () => JSX.Element>> = {
  leads: LeadsPage,
  staff: StaffPage,
  settings: SettingsPage,
  bm: BmPage,
};

const LEADS_ITEM = NAV.find((i) => i.key === "leads") as NavItem;
const STAFF_ITEM = NAV.find((i) => i.key === "staff") as NavItem;

/** Chặn màn hình khi vai trò không có quyền. Backend vẫn kiểm tra lại mọi API. */
function Screen({ item, children }: { item: NavItem; children: ReactNode }) {
  const me = useOutletContext<Me>();
  if (!canSee(item, me.permissions)) return <PlaceholderPage item={item} />;
  return <>{children}</>;
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

function DesktopLayout() {
  return (
    <RequireAuth>
      {(me) => (
        <div className="shell">
          <Sidebar me={me} />
          <main className="main">
            <Outlet context={me} />
          </main>
        </div>
      )}
    </RequireAuth>
  );
}

function HomeRedirect() {
  const me = useOutletContext<Me>();
  return <Navigate to={homePath(me.permissions)} replace />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/change-password"
            element={<RequireAuth allowPasswordChange>{(me) => <ChangePasswordPage me={me} />}</RequireAuth>}
          />
          <Route path="/m/*" element={<RequireAuth>{(me) => <MobileShell me={me} />}</RequireAuth>} />
          <Route element={<DesktopLayout />}>
            <Route index element={<HomeRedirect />} />
            {NAV.filter((item) => !item.later).map((item) => {
              const Done = SCREENS[item.key];
              return (
                <Route
                  key={item.key}
                  path={item.path}
                  element={Done ? <Screen item={item}><Done /></Screen> : <PlaceholderPage item={item} />}
                />
              );
            })}
            <Route
              path="/leads/:id"
              element={
                <Screen item={LEADS_ITEM}>
                  <LeadDetailPage />
                </Screen>
              }
            />
            <Route
              path="/staff/:id"
              element={
                <Screen item={STAFF_ITEM}>
                  <StaffDetailPage />
                </Screen>
              }
            />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
