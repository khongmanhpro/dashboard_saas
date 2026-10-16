export type Role = "owner" | "manager" | "team_lead" | "staff" | "viewer";
export type Scope = "all" | "team" | "own";

export interface Me {
  user: { id: string; email: string; full_name: string };
  workspace: { id: string; name: string; timezone: string };
  member: { id: string; role: Role; team_id: string | null };
  must_change_password: boolean;
  /** {quyền: phạm vi}, ví dụ {"lead.view": "own"} */
  permissions: Record<string, Scope>;
}

export interface LoginResponse extends Me {
  csrf_token: string;
}

export interface PublicConfig {
  mock_mode: boolean;
  app_env: string;
}
