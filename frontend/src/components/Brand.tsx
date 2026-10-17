import { t } from "../i18n";

/** Logo và tên sản phẩm (docs/brand/gocybertech-logo.png), dùng ở menu trái và trang đăng nhập. */
export function Brand() {
  return (
    <div className="brand">
      <img className="brand__logo" src="/brand/logo-mark.png" alt="" width="49" height="32" />
      <div className="brand__name" aria-label={t.app.name}>
        <span className="brand__name-main">{t.app.nameMain}</span>
        <span className="brand__name-accent">{t.app.nameAccent}</span>
      </div>
    </div>
  );
}
