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

async function weight(page: Page, key: string): Promise<number> {
  return Number((await page.getByTestId(`weight-${key}`).innerText()).replace("%", ""));
}

async function step(page: Page, label: string, action: "Tăng 5" | "Giảm 5", times: number) {
  const group = page.getByRole("group", { name: `Trọng số ${label}` });
  for (let i = 0; i < times; i++) await group.getByRole("button", { name: action }).click();
}

test("Chủ sở hữu đổi trọng số: xem thử khớp bảng xếp hạng sau khi lưu", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/staff");
  await page.getByRole("button", { name: "Tính lại ngay" }).click();
  await expect(page.getByTestId("staff-row").first()).toBeVisible();

  await page.goto("/settings");
  // Đổi sang bộ trọng số khác bộ đang lưu (kể cả khi lần chạy trước dừng giữa chừng).
  await expect(page.getByTestId("weight-response_speed")).toBeVisible();
  const speedSaved = await weight(page, "response_speed");
  await page.getByRole("button", { name: "Về mặc định" }).click();
  const times = speedSaved === 35 ? 1 : 2;
  await step(page, "Tốc độ trả lời", "Tăng 5", times);
  await step(page, "Tỉ lệ chốt", "Giảm 5", times);
  await expect(page.getByTestId("weights-total")).toHaveText("Tổng 100%");

  await expect(page.locator(".preview")).toHaveAttribute("aria-busy", "false");
  const rows = page.getByTestId("preview-row");
  await expect(rows.first()).toBeVisible();
  const expected = new Map<string, string>();
  for (const row of await rows.all()) {
    const name = (await row.locator("span").first().innerText()).trim();
    expected.set(name, (await row.getByTestId("preview-new").innerText()).trim());
  }
  expect(expected.size).toBeGreaterThanOrEqual(2);

  await page.getByRole("button", { name: "Lưu công thức" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu và tính lại điểm." })).toBeVisible();

  await page.goto("/staff");
  for (const [name, score] of expected) {
    const row = page.getByTestId("staff-row").filter({ hasText: name });
    await expect(row.locator(".score-cell b")).toHaveText(score);
  }

  // Trả công thức về mặc định để lần chạy sau bắt đầu giống nhau.
  await page.goto("/settings");
  await page.getByRole("button", { name: "Về mặc định" }).click();
  await page.getByRole("button", { name: "Lưu công thức" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu và tính lại điểm." })).toBeVisible();
});

test("Chủ sở hữu đổi ngưỡng chấm điểm: xem thử khớp bảng xếp hạng sau khi lưu", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/settings");
  await page.getByRole("button", { name: "Về mặc định" }).click();
  const closeFull = page.getByTestId("threshold-close_rate_full");
  await expect(closeFull).toHaveValue("30");
  await expect(page.locator(".preview")).toHaveAttribute("aria-busy", "false");
  const before = new Map<string, string>();
  for (const row of await page.getByTestId("preview-row").all()) {
    before.set((await row.locator("span").first().innerText()).trim(), (await row.getByTestId("preview-new").innerText()).trim());
  }

  // Ngưỡng ngược (0 điểm ≥ 100 điểm): không cho lưu.
  await page.getByTestId("threshold-close_rate_zero").fill("40");
  await expect(page.getByRole("button", { name: /Ngưỡng chưa hợp lệ/ })).toBeDisabled();
  await page.getByTestId("threshold-close_rate_zero").fill("5");

  // Nâng ngưỡng 100 điểm của tỉ lệ chốt: điểm xem thử thấp hơn, khớp bảng xếp hạng sau khi lưu.
  await closeFull.fill("80");
  await expect(page.locator(".preview")).toHaveAttribute("aria-busy", "false");
  const expected = new Map<string, string>();
  for (const row of await page.getByTestId("preview-row").all()) {
    const name = (await row.locator("span").first().innerText()).trim();
    expected.set(name, (await row.getByTestId("preview-new").innerText()).trim());
  }
  expect(expected.size).toBeGreaterThanOrEqual(1);
  const [someone, lowered] = [...expected.entries()][0]!;
  expect(Number(lowered.replace(",", "."))).toBeLessThanOrEqual(Number((before.get(someone) ?? "100").replace(",", ".")));

  await page.getByRole("button", { name: "Lưu công thức" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu và tính lại điểm." })).toBeVisible();
  await page.goto("/staff");
  for (const [name, score] of expected) {
    const row = page.getByTestId("staff-row").filter({ hasText: name });
    await expect(row.locator(".score-cell b")).toHaveText(score);
  }

  await page.goto("/settings");
  await page.getByRole("button", { name: "Về mặc định" }).click();
  await page.getByRole("button", { name: "Lưu công thức" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã lưu và tính lại điểm." })).toBeVisible();
});

test("Nhân viên chỉ thấy điểm của mình, người khác chỉ tên và hạng", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/staff");
  await page.getByRole("button", { name: "Tính lại ngay" }).click();
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL("/login");

  await login(page, "staff");
  await page.goto("/staff");
  const self = page.getByTestId("staff-row").filter({ hasText: "[Nhân viên E2E]" });
  await expect(self.getByText("Bạn")).toBeVisible();
  await expect(self.locator(".score-cell b")).toHaveText(/\d/);
  const other = page.getByTestId("staff-row").filter({ hasText: "[Trưởng nhóm E2E]" });
  await expect(other).toBeVisible();
  await expect(other.locator(".score-cell")).toHaveCount(0);
  await expect(other.locator("td").nth(4)).toHaveText("—");
  await expect(page.getByText("Khách mới", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".kpis")).toHaveCount(0);
});

test("Quản lý xem công thức nhưng không sửa được", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/settings");
  await expect(page.getByText("Chỉ Chủ sở hữu sửa được công thức điểm.")).toBeVisible();
  await expect(page.getByRole("group", { name: "Trọng số Tỉ lệ chốt" }).getByRole("button", { name: "Tăng 5" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Lưu công thức" })).toHaveCount(0);
});
