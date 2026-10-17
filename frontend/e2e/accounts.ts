export type E2ERole = "owner" | "manager" | "team_lead" | "staff" | "viewer" | "first_login";

export interface E2EAccount {
  email: string;
  password: string;
}

/** Tài khoản do global-setup tạo, truyền qua biến môi trường (không ghi ra file). */
export function account(role: E2ERole): E2EAccount {
  const raw = process.env.E2E_ACCOUNTS;
  if (!raw) throw new Error("E2E_ACCOUNTS chưa được global-setup đặt");
  const accounts = JSON.parse(raw) as Record<E2ERole, E2EAccount>;
  return accounts[role];
}

export interface E2ELeads {
  run: string;
  ids: Record<"flow" | "viewer" | "other" | "mobile_call" | "mobile_later", string>;
}

/** Khách do global-setup tạo cho lần chạy này. */
export function e2eLeads(): E2ELeads {
  const raw = process.env.E2E_LEADS;
  if (!raw) throw new Error("E2E_LEADS chưa được global-setup đặt");
  return JSON.parse(raw) as E2ELeads;
}

export function leadName(key: keyof E2ELeads["ids"]): string {
  return `[Khách E2E ${e2eLeads().run} ${key}]`;
}
