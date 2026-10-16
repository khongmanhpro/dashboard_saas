import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";

import type { E2EAccount, E2ERole } from "./accounts";

const ROOT = resolve(import.meta.dirname, "..", "..");
const ROLES: Array<[E2ERole, string, string, boolean]> = [
  ["owner", "owner", "[Chủ sở hữu E2E]", false],
  ["manager", "manager", "[Quản lý E2E]", false],
  ["team_lead", "team_lead", "[Trưởng nhóm E2E]", false],
  ["staff", "staff", "[Nhân viên E2E]", false],
  ["viewer", "viewer", "[Chỉ xem E2E]", false],
  ["first_login", "staff", "[Nhân viên mới E2E]", true],
];

/**
 * Tạo (hoặc đặt lại) tài khoản test qua CLI backend. Mật khẩu sinh mới mỗi lần chạy,
 * gửi qua stdin, không xuất hiện trên dòng lệnh hay trong file.
 */
export default function globalSetup(): void {
  const accounts = {} as Record<E2ERole, E2EAccount>;
  const payload = {
    workspace: "E2E Playwright",
    accounts: ROLES.map(([key, role, fullName, mustChange]) => {
      const password = `E2e-${randomBytes(12).toString("base64url")}`;
      const email = `e2e-${key.replace("_", "-")}@example.com`;
      accounts[key] = { email, password };
      return { email, full_name: fullName, role, password, must_change_password: mustChange };
    }),
  };
  execFileSync(
    "docker",
    ["compose", "run", "--rm", "-T", "migrate", "python", "-m", "app.cli", "e2e-seed"],
    { cwd: ROOT, input: JSON.stringify(payload), stdio: ["pipe", "ignore", "inherit"] },
  );
  process.env.E2E_ACCOUNTS = JSON.stringify(accounts);
}
