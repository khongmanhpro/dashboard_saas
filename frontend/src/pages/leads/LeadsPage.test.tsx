import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Me } from "../../api/types";
import { OVERDUE_LINK, Sidebar } from "../../components/Sidebar";
import { t } from "../../i18n";
import { LeadsPage } from "./LeadsPage";

vi.mock("../../api/leads", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/leads")>()),
  useLeadSummary: () => ({ data: { total: 5, overdue: 3, unreplied: 1, phone_not_called: 0, new_today: 0, by_status: {} } }),
  useLeadList: () => ({ data: undefined, isLoading: false, hasNextPage: false }),
  useFilterOptions: () => ({ data: { pages: [], owners: [] } }),
}));
vi.mock("../../auth/useAuth", () => ({
  useLogout: () => ({ isPending: false, mutate: () => undefined }),
  usePublicConfig: () => ({ data: undefined }),
}));

const me: Me = {
  user: { id: "u", email: "nv186@example.test", full_name: "[Nhân viên 186]" },
  workspace: { id: "w", name: "[Workspace]", timezone: "Asia/Ho_Chi_Minh" },
  member: { id: "m", role: "manager", team_id: null },
  must_change_password: false,
  permissions: { "lead.view": "all" },
};

function Shell() {
  return (
    <>
      <Sidebar me={me} />
      <main>
        <Outlet context={me} />
      </main>
    </>
  );
}

const chip = (label: string) => screen.getByRole("button", { name: new RegExp(label) });

afterEach(cleanup);

describe("số đỏ ở menu Khách hàng", () => {
  it("bấm lại khi đường dẫn không đổi vẫn đưa bộ lọc về Quá 48 giờ", async () => {
    const router = createMemoryRouter([{ element: <Shell />, children: [{ path: "/leads", element: <LeadsPage /> }] }], {
      initialEntries: [OVERDUE_LINK],
    });
    render(<RouterProvider router={router} />);
    expect(chip(t.leads.chips.overdue).getAttribute("aria-pressed")).toBe("true");

    // Đổi chip bằng tay: đường dẫn vẫn là OVERDUE_LINK.
    fireEvent.click(chip(t.leads.chips.unreplied));
    expect(chip(t.leads.chips.unreplied).getAttribute("aria-pressed")).toBe("true");

    await act(async () => {
      fireEvent.click(screen.getByTestId("nav-overdue"));
    });
    expect(chip(t.leads.chips.overdue).getAttribute("aria-pressed")).toBe("true");
    expect(chip(t.leads.chips.unreplied).getAttribute("aria-pressed")).toBe("false");
  });
});
