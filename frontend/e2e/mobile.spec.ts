import { expect, test } from "@playwright/test";

import { account } from "./accounts";

test("nhân viên mở /m trên điện thoại", async ({ page }) => {
  const { email, password } = account("staff");
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).toHaveURL("/staff");

  await page.goto("/m");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Khách của tôi");
  await expect(page.locator(".badge-sample")).toBeVisible();
  // Không bị tràn ngang trên màn hình hẹp.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
