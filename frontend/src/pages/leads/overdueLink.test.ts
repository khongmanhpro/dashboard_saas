import { describe, expect, it } from "vitest";

import { OVERDUE_LINK } from "../../components/Sidebar";
import { filtersFromUrl } from "./LeadsPage";

describe("số đỏ ở menu Khách hàng", () => {
  it("mở Khách hàng với đúng phạm vi của số đỏ: Quá 48 giờ, tất cả thời gian", () => {
    const url = new URL(OVERDUE_LINK, "http://localhost");
    expect(url.pathname).toBe("/leads");
    expect(filtersFromUrl(url.searchParams)).toMatchObject({ chip: "overdue", period: "all" });
  });
});
