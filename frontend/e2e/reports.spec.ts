import { expect, test, type Page } from "@playwright/test";

import { account, type E2ERole } from "./accounts";

async function login(page: Page, role: E2ERole) {
  const { email, password } = account(role);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).not.toHaveURL("/login");
}

test("Chủ sở hữu xem Tổng quan, bấm chỗ rơi trong phễu mở đúng danh sách khách", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Tổng quan", level: 1 })).toBeVisible();
  const kpis = page.getByTestId("overview-kpis");
  await expect(kpis.getByText("Khách mới")).toBeVisible();
  await expect(kpis.getByText("Chi phí / khách chốt")).toBeVisible();
  await expect(page.getByTestId("overview-campaigns").getByText("[E2E - Tin nhắn]")).toBeVisible();
  await expect(page.getByTestId("alert-overdue")).toBeVisible();

  await page.getByRole("button", { name: "30 ngày" }).click();
  await expect(page.getByRole("button", { name: "30 ngày" })).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("overview-funnel").getByRole("link", { name: /chưa trả lời/ }).click();
  await expect(page).toHaveURL(/\/leads\?chip=unreplied&period=30d/);
  await expect(page.getByRole("button", { name: /Chưa trả lời/ })).toHaveAttribute("aria-pressed", "true");
});

test("Trưởng nhóm xem Tổng quan nhóm mình, không thấy chi phí quảng cáo", async ({ page }) => {
  await login(page, "team_lead");
  await page.goto("/overview");
  await expect(page.getByTestId("overview-kpis").getByText("Khách mới")).toBeVisible();
  await expect(page.getByTestId("overview-kpis").getByText("Chi phí / khách chốt")).toHaveCount(0);
  await expect(page.getByTestId("overview-campaigns")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Quảng cáo" })).toHaveCount(0);
  await page.goto("/ads");
  await expect(page.getByText("Vai trò của bạn không xem được màn hình này.")).toBeVisible();
});

test("Fanpage: lọc, mở chi tiết Trang, tab làm sau", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/pages");
  const table = page.getByTestId("pages-table");
  await expect(table.getByText("[Trang E2E 1]")).toBeVisible();
  await page.getByRole("searchbox").fill("E2E 2");
  await expect(table.getByText("[Trang E2E 1]")).toHaveCount(0);
  await expect(table.getByText("[Trang E2E 2]")).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await table.getByRole("link", { name: /\[Trang E2E 1\]/ }).click();
  await expect(page).toHaveURL(/\/pages\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "[Trang E2E 1]", level: 1 })).toBeVisible();
  await expect(page.getByText("Chỉ số 30 ngày").or(page.getByLabel("Chỉ số 30 ngày"))).toBeVisible();
  await page.getByRole("tab", { name: /Lịch đăng/ }).click();
  await expect(page.getByText("Phần này làm ở giai đoạn sau.")).toBeVisible();
  await page.getByRole("link", { name: "‹ Tất cả Fanpage" }).click();
  await expect(page).toHaveURL("/pages");
});

test("Quảng cáo: chiến dịch có khách và khách chốt, đổi cấp báo cáo; Chỉ xem không bật được cảnh báo", async ({ page }) => {
  await login(page, "viewer");
  await page.goto("/ads");
  const table = page.getByTestId("ads-table");
  const row = table.getByTestId("ads-row").filter({ hasText: "[E2E - Tin nhắn]" });
  await expect(row).toBeVisible();
  await expect(row.getByText("Đang chạy")).toBeVisible();
  await page.getByRole("tab", { name: "Quảng cáo", exact: true }).click();
  await expect(table.getByText("[E2E - Quảng cáo ảnh]")).toBeVisible();
  const rules = page.getByTestId("ads-rules");
  await expect(rules.getByRole("switch", { name: "Chi phí/kết quả cao" })).toBeDisabled();
});

test("Chủ sở hữu cấu hình Telegram: chat ID sai báo lỗi, đúng thì lưu và gửi thử", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/settings");
  const chat = page.getByLabel("Telegram của sếp (chat ID)");
  await chat.fill("abc");
  await page.getByRole("button", { name: "Lưu cảnh báo" }).click();
  await expect(page.getByText("Chat ID không hợp lệ.", { exact: false })).toBeVisible();
  await chat.fill("-1009876543210");
  await page.getByRole("button", { name: "Lưu cảnh báo" }).click();
  await expect(page.getByText("Đã lưu.")).toBeVisible();
  await page.getByRole("button", { name: "Gửi thử" }).click();
  await expect(page.getByText("Chế độ giả lập: tin thử không gửi thật.")).toBeVisible();
});

test("Màn hình hẹp: Tổng quan đổi sang bố cục điện thoại, có thanh menu dưới", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "owner");
  await page.goto("/overview");
  await expect(page.getByRole("navigation", { name: "Điều hướng chính" })).toBeHidden();
  const nav = page.getByRole("navigation", { name: "Điều hướng" });
  await expect(nav).toBeVisible();
  await expect(page.getByRole("heading", { name: "Khách chốt theo ngày", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Khách mới và khách chốt theo ngày" })).toBeHidden();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await nav.getByRole("link", { name: "Quảng cáo" }).click();
  await expect(page).toHaveURL("/ads");
});
