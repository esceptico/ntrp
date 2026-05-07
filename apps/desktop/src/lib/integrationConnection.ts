export interface ServiceConnectionLike {
  id: string;
  name: string;
  connected: boolean;
  from_env: boolean;
  key_hint?: string | null;
}

export interface GmailAccountLike {
  email?: string | null;
  token_file: string;
  has_send_scope?: boolean;
  error?: string;
}

export function serviceConnectionLabel(service: ServiceConnectionLike): string {
  if (!service.connected) return "Not connected";
  if (service.from_env) return "Connected via env";
  if (service.key_hint) return service.key_hint;
  return "Connected";
}

export function serviceActionLabel(service: ServiceConnectionLike): string {
  if (service.connected && service.from_env) return "Env-managed";
  if (service.connected) return "Disconnect";
  return "Connect";
}

export function gmailAccountSummary(accounts: readonly GmailAccountLike[]): string {
  const count = accounts.length;
  if (count === 0) return "No accounts";
  return `${count} ${count === 1 ? "account" : "accounts"}`;
}
