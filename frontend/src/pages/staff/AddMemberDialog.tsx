import { useState } from "react";

import { ApiError } from "../../api/client";
import { useCreateMember, useTeams } from "../../api/bms";
import type { Me, Role } from "../../api/types";
import { errorMessage, format, t } from "../../i18n";

function randomPassword(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("") + "-Tm";
}

/** Thêm một nhân viên (API tạo thành viên của Bước 1). Quản lý chỉ cấp được Trưởng nhóm, Nhân viên, Chỉ xem. */
export function AddMemberDialog({ me, onClose }: { me: Me; onClose: () => void }) {
  const roles: Role[] = me.member.role === "owner" ? ["staff", "team_lead", "viewer", "manager", "owner"] : ["staff", "team_lead", "viewer"];
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("staff");
  const [teamId, setTeamId] = useState("");
  const [password, setPassword] = useState(randomPassword);
  const teams = useTeams(true);
  const create = useCreateMember();
  return (
    <div className="dialog-backdrop">
      <form
        className="dialog card m-stack"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-member-title"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate({ email: email.trim(), full_name: name.trim(), role, team_id: teamId || null, temp_password: password });
        }}
      >
        <div className="section-head section-head--row">
          <h2 id="add-member-title">{t.addMember.title}</h2>
          <button type="button" className="link-btn" aria-label={t.addMember.cancel} onClick={onClose}>
            ×
          </button>
        </div>
        <div className="field">
          <label htmlFor="m-name">{t.addMember.name}</label>
          <input id="m-name" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="m-email">{t.addMember.email}</label>
          <input id="m-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="m-role">{t.addMember.role}</label>
          <select id="m-role" className="form-select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {t.roles[r]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="m-team">{t.addMember.team}</label>
          <select id="m-team" className="form-select" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">{t.addMember.noTeam}</option>
            {teams.data?.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="m-password">{t.addMember.password}</label>
          <input id="m-password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />
          <span className="field__hint">{t.addMember.passwordNote}</span>
        </div>
        {create.error instanceof ApiError ? (
          <div className="alert alert--error" role="alert">
            {errorMessage(create.error.code)}
          </div>
        ) : null}
        {create.isSuccess ? (
          <div className="alert alert--ok" role="status">
            {format(t.addMember.done, { name })}
          </div>
        ) : null}
        <div className="bm-panel__actions">
          <button type="button" className="btn" onClick={onClose}>
            {t.addMember.cancel}
          </button>
          <button type="submit" className="btn btn--primary" disabled={create.isPending || create.isSuccess}>
            {create.isPending ? t.addMember.saving : t.addMember.save}
          </button>
        </div>
      </form>
    </div>
  );
}
