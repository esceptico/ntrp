import type { Config } from "../types.js";
import { api } from "./fetch.js";

export interface GoogleAccount {
  email: string | null;
  token_file: string;
  has_send_scope?: boolean;
  error?: string;
}

export async function getGoogleAccounts(config: Config): Promise<{ accounts: GoogleAccount[] }> {
  return api.get(`${config.serverUrl}/gmail/accounts`);
}

export async function addGoogleAccount(config: Config): Promise<{ email: string; status: string }> {
  return api.post(`${config.serverUrl}/gmail/add`);
}

export async function removeGoogleAccount(config: Config, tokenFile: string): Promise<{ email: string | null; status: string }> {
  return api.delete(`${config.serverUrl}/gmail/${tokenFile}`);
}
