import { describe, expect, it } from "vitest";

import type { Scope } from "../api/types";
import { homePath, visibleNav } from "./nav";

// Quyền khớp với backend/app/core/rbac.py (backend trả về qua /api/me).
const PERMS: Record<string, Record<string, Scope>> = {
  owner: Object.fromEntries(
    [
      "bm.connect", "bm.view", "score_formula.edit", "billing.manage", "settings.manage", "page.assign",
      "team.view", "team.manage", "member.view", "member.manage", "lead.view", "lead.update",
      "lead.reassign", "lead.phone.view", "reminder.send", "ads.cost.view", "leaderboard.view", "report.view",
    ].map((p) => [p, "all" as Scope]),
  ),
  manager: Object.fromEntries(
    [
      "bm.view", "page.assign", "team.view", "team.manage", "member.view", "member.manage", "lead.view",
      "lead.update", "lead.reassign", "lead.phone.view", "reminder.send", "ads.cost.view",
      "leaderboard.view", "report.view",
    ].map((p) => [p, "all" as Scope]),
  ),
  team_lead: {
    "team.view": "team", "member.view": "team", "lead.view": "team", "lead.phone.view": "team",
    "lead.update": "own", "reminder.send": "team", "leaderboard.view": "team", "report.view": "team",
  },
  staff: { "lead.view": "own", "lead.update": "own", "lead.phone.view": "own", "leaderboard.view": "own" },
  viewer: {
    "team.view": "all", "member.view": "all", "lead.view": "all", "ads.cost.view": "all",
    "leaderboard.view": "all", "report.view": "all",
  },
};

const keys = (role: string) => visibleNav(PERMS[role]!).map((i) => i.key);

describe("menu theo vai trò", () => {
  it("chủ sở hữu và quản lý thấy đủ menu", () => {
    const all = ["overview", "staff", "leads", "pages", "ads", "inbox", "bm", "settings"];
    expect(keys("owner")).toEqual(all);
    expect(keys("manager")).toEqual(all);
  });

  it("trưởng nhóm không thấy quảng cáo, kết nối BM, cài đặt", () => {
    expect(keys("team_lead")).toEqual(["overview", "staff", "leads", "pages", "inbox"]);
  });

  it("nhân viên chỉ thấy bảng xếp hạng và khách của mình", () => {
    expect(keys("staff")).toEqual(["staff", "leads", "inbox"]);
  });

  it("chỉ xem thấy báo cáo và chi phí, không thấy quản trị", () => {
    expect(keys("viewer")).toEqual(["overview", "staff", "leads", "pages", "ads", "inbox"]);
  });

  it("trang đầu sau đăng nhập là mục đầu tiên được phép", () => {
    expect(homePath(PERMS.owner!)).toBe("/overview");
    expect(homePath(PERMS.staff!)).toBe("/staff");
    expect(homePath({})).toBe("/m");
  });
});
