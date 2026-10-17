import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { Me } from "../api/types";
import { homePath } from "../app/nav";
import { useLogout } from "../auth/useAuth";
import { t } from "../i18n";
import { disablePush, enablePush, isIosBrowserTab, pushState, type PushState } from "./push";

export function AccountScreen({ me }: { me: Me }) {
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const logout = useLogout();
  const navigate = useNavigate();
  const desktop = homePath(me.permissions);

  useEffect(() => {
    pushState().then(setState, () => setState("unsupported"));
  }, []);

  const toggle = async () => {
    setBusy(true);
    try {
      setState(state === "on" ? await disablePush() : await enablePush());
    } finally {
      setBusy(false);
    }
  };

  let pushText: string = state === "on" ? t.mobile.account.pushOn : t.mobile.account.pushOff;
  if (state === "unsupported") pushText = isIosBrowserTab() ? t.mobile.account.iosHint : t.mobile.account.pushUnsupported;
  if (state === "not_configured") pushText = t.mobile.account.pushNotConfigured;
  if (state === "denied") pushText = t.mobile.account.pushDenied;

  return (
    <div className="m-pad m-stack">
      <h1 className="m-title">{t.mobile.account.title}</h1>
      <div className="card">
        <b>{me.user.full_name}</b>
        <div className="muted">
          {t.roles[me.member.role]} · {me.workspace.name}
        </div>
      </div>
      <div className="card m-stack">
        <b>{t.mobile.account.push}</b>
        <span className="note" data-testid="push-state">
          {pushText}
        </span>
        {state === "on" || state === "off" ? (
          <button type="button" className="btn btn--block" disabled={busy} onClick={() => void toggle()}>
            {state === "on" ? t.mobile.account.disable : t.mobile.account.enable}
          </button>
        ) : null}
        {isIosBrowserTab() && state !== "unsupported" ? <span className="note">{t.mobile.account.iosHint}</span> : null}
        <span className="note">{t.mobile.account.installHint}</span>
      </div>
      <Link className="btn btn--block" to="/change-password">
        {t.mobile.account.changePassword}
      </Link>
      {desktop !== "/m" ? (
        <Link className="btn btn--block" to={desktop}>
          {t.mobile.desktop}
        </Link>
      ) : null}
      <button
        type="button"
        className="btn btn--block"
        disabled={logout.isPending}
        onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login", { replace: true }) })}
      >
        {t.account.logout}
      </button>
    </div>
  );
}
