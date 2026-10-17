import { expect, test } from "@playwright/test";

// Kiểm tra điều kiện cài lên màn hình chính bằng chính Chrome (CDP), không cần điện thoại.
// Cài thật trên Android/iPhone cần HTTPS: xem README, mục "Ứng dụng điện thoại".
test("app đủ điều kiện cài lên màn hình chính", async ({ page, browserName }, info) => {
  test.skip(browserName !== "chromium" || info.project.name !== "desktop", "chỉ Chrome mới có CDP");
  await page.goto("/login");
  const manifest = await page.evaluate(async () => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    return link ? (await fetch(link.href)).json() : null;
  });
  expect(manifest).toMatchObject({ start_url: "/m", display: "standalone" });
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
  expect(scope).toMatch(/\/$/);

  const cdp = await page.context().newCDPSession(page);
  const { installabilityErrors } = await cdp.send("Page.getInstallabilityErrors");
  expect(installabilityErrors).toEqual([]);

  // Service worker không lưu dữ liệu API.
  const cachedApi = await page.evaluate(async () => {
    const keys = await caches.keys();
    const urls = (await Promise.all(keys.map(async (k) => (await caches.open(k)).keys()))).flat();
    return urls.map((r) => r.url).filter((u) => u.includes("/api/"));
  });
  expect(cachedApi).toEqual([]);
});
