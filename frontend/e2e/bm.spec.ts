import { createHmac, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { account, type E2ERole } from "./accounts";

// Mã giả của client Graph giả (backend/tests/fixtures/meta/graph_mock.json), chỉ chạy khi MOCK_MODE=true.
const E2E_TOKEN = "MOCK-BM-E2E";
const E2E_PAGE = { id: "100000000000201", name: "[Trang E2E BM 1]" };

async function login(page: Page, role: E2ERole) {
  const { email, password } = account(role);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page).not.toHaveURL("/login");
}

/** Bí mật ứng dụng Meta của máy dev (.env) để ký webhook giả như Meta. */
function appSecret(): string {
  const env = readFileSync(resolve(import.meta.dirname, "..", "..", ".env"), "utf8");
  const line = env.split("\n").find((l) => l.startsWith("META_APP_SECRET="));
  return line?.slice("META_APP_SECRET=".length).trim() ?? "";
}

test("Chủ sở hữu thêm BM thứ hai, gán Trang mới, khách nhắn vào được tính cho người được gán", async ({ page }) => {
  await login(page, "owner");
  await page.goto("/bm");
  await page.getByRole("button", { name: "+ Thêm BM" }).click();
  await page.getByRole("button", { name: "Đã tạo, tiếp tục" }).click();
  await page.getByRole("button", { name: "Đã gán, tiếp tục" }).click();
  await page.getByLabel("Mã truy cập").fill(E2E_TOKEN);
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).click();
  const checks = page.getByTestId("bm-checks");
  await expect(checks.getByText("Mã hợp lệ")).toBeVisible();
  await expect(checks.getByText("Đọc được 2 Trang")).toBeVisible();
  await page.getByRole("button", { name: "Lưu & bắt đầu đồng bộ" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã kết nối" })).toBeVisible();
  await expect(page.getByTestId("bm-row").filter({ hasText: "[BM E2E thứ hai]" })).toBeVisible();
  // Mã không bao giờ hiện lại trên giao diện.
  await expect(page.getByText(E2E_TOKEN)).toHaveCount(0);

  await page.getByRole("button", { name: "Tất cả Trang" }).click();
  const row = page.getByTestId("page-row").filter({ hasText: E2E_PAGE.name });
  const select = row.getByRole("combobox");
  await select.selectOption({ label: "[Quản lý E2E]" });
  await expect(select).toHaveValue(/.+/);
  await expect(row.getByRole("alert")).toHaveCount(0);

  // Gửi webhook giả (ký bằng META_APP_SECRET như Meta) vào Trang của BM mới.
  const psid = `e2e-bm-${randomBytes(3).toString("hex")}`;
  const body = JSON.stringify({
    object: "page",
    entry: [
      {
        id: E2E_PAGE.id,
        time: Date.now(),
        messaging: [
          {
            sender: { id: psid },
            recipient: { id: E2E_PAGE.id },
            timestamp: Date.now(),
            message: { mid: `m_${psid}`, text: "[Tin nhắn E2E BM]" },
          },
        ],
      },
    ],
  });
  const signature = "sha256=" + createHmac("sha256", appSecret()).update(body).digest("hex");
  const sent = await page.request.post("http://localhost:8000/webhooks/meta", {
    data: body,
    headers: { "Content-Type": "application/json", "X-Hub-Signature-256": signature },
  });
  expect(sent.status()).toBe(200);

  await page.goto("/leads");
  await page.getByRole("button", { name: "Dạng bảng" }).click();
  const name = `[Khách ${psid.slice(-4)}]`; // tên lấy qua Graph API (giả)
  await expect(async () => {
    await page.getByLabel("Tìm khách").fill(name);
    await expect(page.getByTestId("lead-row").filter({ hasText: name })).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 20_000 });
  await expect(page.getByTestId("lead-row").filter({ hasText: name })).toContainText("[Quản lý E2E]");
});

test("Quản lý xem BM nhưng không thấy nút dán mã", async ({ page }) => {
  await login(page, "manager");
  await page.goto("/bm");
  await expect(page.getByRole("heading", { name: "Kết nối Business Manager" })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ Thêm BM" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cập nhật mã" })).toHaveCount(0);
});

test("Quản lý nhập nhân viên từ file Excel mẫu", async ({ page }) => {
  await login(page, "manager");
  const template = await page.request.get("/api/imports/members/template");
  expect(template.status()).toBe(200);
  await page.goto("/staff");
  await page.getByRole("button", { name: "Nhập từ Excel" }).click();
  await page.getByLabel("Chọn file .xlsx").setInputFiles({
    name: "mau.xlsx",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: await template.body(),
  });
  const dialog = page.getByRole("dialog", { name: "Nhập nhân viên từ Excel" });
  await expect(dialog.getByTestId("import-row")).toHaveCount(2);
  await expect(dialog.getByText("2 hợp lệ")).toBeVisible();
  await dialog.getByRole("button", { name: /Nhập 2 nhân viên/ }).click();
  await expect(dialog.getByRole("status")).toContainText("bỏ qua 0 dòng");
});
