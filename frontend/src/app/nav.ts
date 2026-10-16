import type { Scope } from "../api/types";
import type { IconName } from "../components/Icon";
import { t } from "../i18n";

export interface NavItem {
  key: keyof typeof t.nav;
  path: string;
  icon: IconName;
  /** Hiện mục này nếu có ÍT NHẤT MỘT quyền trong danh sách. Backend vẫn kiểm tra lại. */
  anyOf: string[];
  /** Bước trong CLAUDE.md mục 8 sẽ làm màn hình này. */
  step: number;
  group: "main" | "admin";
  /** Chức năng giai đoạn sau: hiện mờ, không bấm được. */
  later?: boolean;
}

export const NAV: NavItem[] = [
  { key: "overview", path: "/overview", icon: "overview", anyOf: ["report.view"], step: 7, group: "main" },
  { key: "staff", path: "/staff", icon: "staff", anyOf: ["leaderboard.view"], step: 4, group: "main" },
  { key: "leads", path: "/leads", icon: "leads", anyOf: ["lead.view"], step: 3, group: "main" },
  { key: "pages", path: "/pages", icon: "pages", anyOf: ["report.view"], step: 7, group: "main" },
  { key: "ads", path: "/ads", icon: "ads", anyOf: ["ads.cost.view"], step: 7, group: "main" },
  { key: "inbox", path: "/inbox", icon: "inbox", anyOf: [], step: 0, group: "main", later: true },
  { key: "bm", path: "/bm", icon: "bm", anyOf: ["bm.view"], step: 6, group: "admin" },
  { key: "settings", path: "/settings", icon: "settings", anyOf: ["settings.manage", "team.manage"], step: 4, group: "admin" },
];

export function canSee(item: NavItem, permissions: Record<string, Scope>): boolean {
  return item.anyOf.some((perm) => perm in permissions);
}

export function visibleNav(permissions: Record<string, Scope>): NavItem[] {
  return NAV.filter((item) => item.later || canSee(item, permissions));
}

/** Trang đầu tiên sau khi đăng nhập: mục đầu tiên được phép xem. */
export function homePath(permissions: Record<string, Scope>): string {
  return NAV.find((item) => !item.later && canSee(item, permissions))?.path ?? "/m";
}
