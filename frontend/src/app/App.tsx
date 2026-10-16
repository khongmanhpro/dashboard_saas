import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useOutletContext } from "react-router-dom";

import type { Me } from "../api/types";
import { RequireAuth } from "../auth/guards";
import { Sidebar } from "../components/Sidebar";
import { MobileShell } from "../mobile/MobileShell";
import { ChangePasswordPage } from "../pages/ChangePasswordPage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { homePath, NAV } from "./nav";

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
            {NAV.filter((item) => !item.later).map((item) => (
              <Route key={item.key} path={item.path} element={<PlaceholderPage item={item} />} />
            ))}
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
