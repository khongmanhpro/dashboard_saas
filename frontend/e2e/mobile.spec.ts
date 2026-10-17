import { expect, test, type Page } from "@playwright/test";

import { account, e2eLeads, leadName, type E2ERole } from "./accounts";

async function login(page: Page, role: E2ERole) {
  const { email, password } = account(role);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).not.toHaveURL("/login");
}

test("nhân viên mở /m trên điện thoại", async ({ page }) => {
  await login(page, "staff");
  await page.goto("/m");
  await expect(page.getByRole("tablist", { name: "Danh sách khách" })).toBeVisible();
  await expect(page.locator(".badge-sample")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Điều hướng" })).toBeVisible();
  // Không bị tràn ngang trên màn hình hẹp.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test.describe("trên điện thoại", () => {
  // Các test này đổi dữ liệu khách nên chỉ chạy một lần, ở khung điện thoại.
  test.skip(({ isMobile }) => !isMobile, "chỉ chạy ở project mobile");

  test("Gọi → Chốt: khách sang tab Đã xong", async ({ page }) => {
    await login(page, "staff");
    await page.goto("/m");
    // Không mở trình gọi điện thật trong trình duyệt test; onClick của React vẫn chạy.
    await page.evaluate(() =>
      document.addEventListener(
        "click",
        (e) => {
          if ((e.target as Element).closest('a[href^="tel:"]')) e.preventDefault();
        },
        true,
      ),
    );
    const card = page.getByTestId("m-card").filter({ hasText: leadName("mobile_call") });
    await expect(card).toBeVisible();
    await expect(card.getByText("Có SĐT · chưa gọi")).toBeVisible();
    await card.getByRole("link", { name: "Gọi" }).click();
    await expect(card.getByRole("link", { name: "✓ Đã gọi" })).toBeVisible();

    await card.getByRole("button", { name: "Chốt" }).click();
    const sheet = page.getByRole("dialog", { name: "Chốt đơn" });
    await sheet.getByLabel("Giá trị đơn").fill("2450000");
    await sheet.getByRole("button", { name: "Lưu" }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByTestId("m-card").filter({ hasText: leadName("mobile_call") })).toHaveCount(0);

    await page.getByRole("tab", { name: /Đã xong/ }).click();
    const done = page.getByTestId("m-card").filter({ hasText: leadName("mobile_call") });
    await expect(done.getByText("Đã chốt · 2.450.000 ₫")).toBeVisible();
  });

  test("Hẹn Mai 9:00: khách sang tab Hẹn lại", async ({ page }) => {
    await login(page, "staff");
    await page.goto("/m");
    const card = page.getByTestId("m-card").filter({ hasText: leadName("mobile_later") });
    await card.getByRole("button", { name: "Hẹn" }).click();
    const sheet = page.getByRole("dialog", { name: "Hẹn gọi lại" });
    await sheet.getByRole("button", { name: "Mai 9:00" }).click();
    await sheet.getByRole("button", { name: "Lưu" }).click();
    await page.getByRole("tab", { name: /Hẹn lại/ }).click();
    await expect(page.getByTestId("m-card").filter({ hasText: leadName("mobile_later") }).getByText(/^hẹn /)).toBeVisible();
  });

  test("Chủ sở hữu bấm Nhắc trên máy tính, nhân viên thấy trong Nhắc việc", async ({ page, browser }) => {
    const desktop = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const boss = await desktop.newPage();
    await login(boss, "owner");
    await boss.goto(`/leads/${e2eLeads().ids.viewer}`);
    await boss.getByRole("button", { name: "Nhắc người phụ trách" }).click();
    await expect(boss.getByRole("status").filter({ hasText: "Đã gửi nhắc việc" })).toBeVisible();
    await desktop.close();

    await login(page, "staff");
    await page.goto("/m");
    await expect(page.getByTestId("m-unread")).toBeVisible();
    await page.getByRole("navigation", { name: "Điều hướng" }).getByRole("link", { name: /Nhắc việc/ }).click();
    const notice = page.getByTestId("m-notice").filter({ hasText: leadName("viewer") }).first();
    await expect(notice).toContainText("nhắc bạn xử lý");
    await notice.click();
    await expect(page).toHaveURL(`/m/leads/${e2eLeads().ids.viewer}`);
    await expect(page.getByRole("heading", { level: 1, name: leadName("viewer") })).toBeVisible();
  });
});

test("máy tính bảng 800px: menu là cột icon, nội dung bên phải", async ({ page, isMobile }) => {
  test.skip(isMobile, "chỉ chạy ở project desktop");
  await page.setViewportSize({ width: 800, height: 900 });
  await login(page, "manager");
  await page.goto("/leads");
  const nav = page.getByRole("navigation", { name: "Điều hướng chính" });
  const link = nav.getByRole("link", { name: "Khách hàng", exact: true });
  await expect(link).toBeVisible();
  const navBox = await nav.boundingBox();
  const mainBox = await page.locator("main").boundingBox();
  expect(navBox?.width).toBeLessThanOrEqual(64);
  expect(mainBox?.x).toBeGreaterThanOrEqual(64);
  expect(mainBox?.y).toBe(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("điện thoại: bộ lọc Khách hàng gom vào nút Lọc", async ({ page, isMobile }) => {
  test.skip(!isMobile, "chỉ chạy ở project mobile");
  await login(page, "manager");
  await page.goto("/leads");
  const main = page.locator("main");
  await expect(main.getByLabel("Nguồn")).toBeHidden();
  const toggle = page.getByTestId("filter-toggle");
  await expect(toggle).toHaveText("Lọc");
  await toggle.click();
  const sheet = page.getByRole("dialog", { name: "Bộ lọc" });
  await sheet.getByLabel("Nguồn").selectOption("ad");
  await sheet.getByRole("button", { name: "Xong" }).click();
  await expect(sheet).toBeHidden();
  await expect(toggle).toHaveText("Lọc (1)");
  await toggle.click();
  await page.getByRole("dialog", { name: "Bộ lọc" }).getByRole("button", { name: "Xóa lọc" }).click();
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveText("Lọc");
});
