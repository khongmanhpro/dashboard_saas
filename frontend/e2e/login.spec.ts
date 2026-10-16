import { expect, test, type Page } from "@playwright/test";

import { account, type E2ERole } from "./accounts";

async function login(page: Page, role: E2ERole) {
  const { email, password } = account(role);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

const MENU = ["Tổng quan", "Nhân viên", "Khách hàng", "Fanpage", "Quảng cáo", "Inbox", "Kết nối BM", "Cài đặt"];

const EXPECTED: Record<Exclude<E2ERole, "first_login">, { home: string; role: string; menu: string[] }> = {
  owner: { home: "/overview", role: "Chủ sở hữu", menu: MENU },
  manager: { home: "/overview", role: "Quản lý", menu: MENU },
  team_lead: {
    home: "/overview",
    role: "Trưởng nhóm",
    menu: ["Tổng quan", "Nhân viên", "Khách hàng", "Fanpage", "Inbox"],
  },
  staff: { home: "/staff", role: "Nhân viên", menu: ["Nhân viên", "Khách hàng", "Inbox"] },
  viewer: {
    home: "/overview",
    role: "Chỉ xem",
    menu: ["Tổng quan", "Nhân viên", "Khách hàng", "Fanpage", "Quảng cáo", "Inbox"],
  },
};

for (const [role, expected] of Object.entries(EXPECTED)) {
  test(`${expected.role}: đăng nhập, thấy đúng menu, đăng xuất`, async ({ page }) => {
    await login(page, role as E2ERole);
    await expect(page).toHaveURL(expected.home);

    const nav = page.getByRole("navigation", { name: "Điều hướng chính" });
    const items = nav.locator(".nav-link");
    await expect(items).toHaveText(expected.menu.map((label) => (label === "Inbox" ? "InboxSau" : label)));
    await expect(page.getByTestId("current-role")).toHaveText(expected.role);
    await expect(page.locator(".badge-sample")).toHaveText("Dữ liệu mẫu");

    await page.getByRole("button", { name: "Đăng xuất" }).click();
    await expect(page).toHaveURL("/login");
    await page.goto(expected.home);
    await expect(page).toHaveURL("/login");
  });
}

test("sai mật khẩu báo lỗi bằng tiếng Việt", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("khong-ton-tai-e2e@example.com");
  await page.getByLabel("Mật khẩu").fill("sai-mat-khau-123");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email hoặc mật khẩu không đúng.");
  await expect(page).toHaveURL("/login");
});

test("nhân viên mở thẳng đường dẫn quản trị thì bị chặn", async ({ page }) => {
  await login(page, "staff");
  await expect(page).toHaveURL("/staff");
  await page.goto("/settings");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Không có quyền");
  // Backend cũng chặn, không chỉ giao diện.
  const status = await page.evaluate(async () => (await fetch("/api/members")).status);
  expect(status).toBe(403);
});

test("lần đăng nhập đầu bắt đổi mật khẩu", async ({ page }) => {
  const { password } = account("first_login");
  await login(page, "first_login");
  await expect(page).toHaveURL("/change-password");
  // Chưa đổi mật khẩu thì không vào được trang khác.
  await page.goto("/staff");
  await expect(page).toHaveURL("/change-password");

  await page.getByLabel("Mật khẩu hiện tại").fill(password);
  await page.getByLabel("Mật khẩu mới", { exact: true }).fill("Mat-khau-moi-E2E-2026");
  await page.getByLabel("Nhập lại mật khẩu mới").fill("khac-nhau-2026");
  await page.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(page.getByRole("alert")).toHaveText("Mật khẩu nhập lại không khớp.");

  await page.getByLabel("Nhập lại mật khẩu mới").fill("Mat-khau-moi-E2E-2026");
  await page.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(page).toHaveURL("/staff");
});
