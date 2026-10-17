import { describe, expect, it } from "vitest";

import type { PageQuery } from "../../api/reports";
import { activeFilterCount, clearedFilters } from "./PagesPage";

const base: PageQuery = { tab: "all", q: "", bm_id: "", team_id: "", sort: "leads", page: 1 };

describe("nút Lọc ở Fanpage", () => {
  it("đổi cách sắp xếp không tính là lọc", () => {
    expect(activeFilterCount({ ...base, sort: "score" })).toBe(0);
    expect(activeFilterCount({ ...base, bm_id: "bm", team_id: "team" })).toBe(2);
  });

  it("Xóa lọc giữ cách sắp xếp", () => {
    const sorted = { ...base, bm_id: "bm", sort: "score" };
    expect({ ...sorted, ...clearedFilters }).toMatchObject({ bm_id: "", team_id: "", sort: "score" });
  });
});
