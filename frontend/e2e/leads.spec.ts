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

test("nhân viên đi trọn luồng Mới → Chốt có giá trị đơn", async ({ page }) => {
  await login(page, "staff");
  await page.getByRole("navigation", { name: "Điều hướng chính" }).getByRole("link", { name: "Khách hàng" }).click();
  await expect(page).toHaveURL("/leads");

  const name = leadName("flow");
  const newColumn = page.getByTestId("column-new");
  await expect(newColumn.getByText(name)).toBeVisible();
  await newColumn.getByText(name).click();

  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByTestId("lead-status")).toHaveText("Mới");
  // Nhân viên phụ trách thấy đủ số, kể cả trong nội dung tin nhắn.
  await expect(page.getByText("số em 0900 000 911")).toBeVisible();
  await expect(page.getByText("Tự nhận ra số điện thoại trong tin nhắn")).toBeVisible();

  const called = page.getByRole("switch", { name: "Đã gọi cho khách" });
  await called.click();
  await expect(called).toHaveAttribute("aria-checked", "true");

  const results = page.getByRole("group", { name: "Kết quả" });
  await results.getByRole("button", { name: "Chốt" }).click();
  await expect(page.getByRole("button", { name: "Nhập giá trị đơn để lưu" })).toBeDisabled();
  await page.getByLabel("Giá trị đơn").fill("2450000");
  await expect(page.getByLabel("Giá trị đơn")).toHaveValue("2.450.000");
  await page.getByRole("button", { name: "Lưu kết quả" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Đã lưu kết quả." })).toBeVisible();
  await expect(page.getByTestId("lead-status")).toHaveText("Chốt");
  await expect(page.getByText("Đổi trạng thái: Mới → Chốt. 2.450.000 ₫")).toBeVisible();

  await page.getByRole("link", { name: "Khách hàng" }).first().click();
  const wonColumn = page.getByTestId("column-won");
  await expect(wonColumn.getByText(name)).toBeVisible();
  await expect(wonColumn.getByText("2.450.000 ₫").first()).toBeVisible();
});

test("Chỉ xem: SĐT bị che, không có ô cập nhật kết quả", async ({ page }) => {
  await login(page, "viewer");
  await page.goto(`/leads/${e2eLeads().ids.viewer}`);
  await expect(page.getByRole("heading", { level: 1, name: leadName("viewer") })).toBeVisible();
  await expect(page.getByText("số em 09•• ••• 922")).toBeVisible();
  await expect(page.getByText("0900 000 922")).toHaveCount(0);
  await expect(page.getByText("Bạn chỉ xem được khách này.")).toBeVisible();
  await expect(page.getByRole("group", { name: "Kết quả" })).toHaveCount(0);
});

test("nhân viên mở thẳng khách của người khác thì bị chặn", async ({ page }) => {
  await login(page, "staff");
  await page.goto(`/leads/${e2eLeads().ids.other}`);
  await expect(page.getByRole("alert")).toHaveText("Không tìm thấy khách, hoặc khách không thuộc phạm vi của bạn.");
  await page.goto("/leads");
  await expect(page.getByText(leadName("other"))).toHaveCount(0);
});

test("dạng bảng và ô lọc nhanh", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/leads");
  await page.getByRole("button", { name: "Dạng bảng" }).click();
  await page.getByLabel("Tìm khách").fill(e2eLeads().run);
  const rows = page.getByTestId("lead-row");
  for (const key of ["flow", "viewer", "other"] as const) {
    await expect(rows.filter({ hasText: leadName(key) })).toBeVisible();
  }
  await page.getByRole("button", { name: /Có SĐT chưa gọi/ }).click();
  await expect(rows.filter({ hasText: leadName("viewer") })).toBeVisible();
  // Khách đã Chốt và đã gọi ở test đầu thì không còn trong ô lọc này.
  await expect(rows.filter({ hasText: leadName("flow") })).toHaveCount(0);
  await page.getByRole("button", { name: "Theo cột" }).click();
});
