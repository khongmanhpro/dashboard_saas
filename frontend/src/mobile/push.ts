// Bật / tắt thông báo đẩy (Web Push). Khóa công khai VAPID lấy từ /api/push/config.
import { api } from "../api/client";

export type PushState = "unsupported" | "not_configured" | "denied" | "off" | "on";

export function pushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** iPhone/iPad chỉ nhận thông báo đẩy khi app được mở từ màn hình chính. */
export function isIosBrowserTab(): boolean {
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone;
  return ios && !standalone;
}

export function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = (value + "=".repeat((4 - (value.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** Đăng ký đẩy hiện có. Không chờ `serviceWorker.ready` (có thể treo khi chưa có service worker). */
async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  return registration ? registration.pushManager.getSubscription() : null;
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const config = await api<{ enabled: boolean; public_key: string | null }>("/api/push/config");
  if (!config.enabled) return "not_configured";
  if (Notification.permission === "denied") return "denied";
  return (await currentSubscription()) ? "on" : "off";
}

export async function enablePush(): Promise<PushState> {
  const config = await api<{ enabled: boolean; public_key: string | null }>("/api/push/config");
  if (!config.enabled || !config.public_key) return "not_configured";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToBytes(config.public_key),
    }));
  await api<void>("/api/push/subscriptions", { method: "POST", body: subscription.toJSON() });
  return "on";
}

/** Tắt trên máy này. Gọi cả khi đăng xuất để máy không còn nhận nhắc việc của người cũ. */
export async function disablePush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const subscription = await currentSubscription();
  if (subscription) {
    await api<void>("/api/push/unsubscribe", { method: "POST", body: { endpoint: subscription.endpoint } }).catch(() => undefined);
    await subscription.unsubscribe();
  }
  return "off";
}
