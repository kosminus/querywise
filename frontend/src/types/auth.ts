export type Role = 'admin' | 'editor' | 'viewer';

export interface User {
  id: string;
  email: string;
  name: string | null;
  status: string;
  last_login_at: string | null;
  created_at: string;
}

export interface WorkspaceMembership {
  team_id: string;
  team_name: string;
  role: Role;
}

export interface Me {
  user: User;
  workspaces: WorkspaceMembership[];
}

export interface AuthProviderInfo {
  name: string;
  supports_password: boolean;
  supports_magic_link: boolean;
  is_sso: boolean;
  disable_auth: boolean;
}

export interface MagicLinkResponse {
  sent: boolean;
  dev_token: string | null;
  dev_verify_url: string | null;
}
