export interface DirectoryPickerOptions {
  defaultPath?: string;
}

export async function selectDirectory(options: DirectoryPickerOptions = {}): Promise<string | null> {
  const picker = window.ntrpDesktop?.dialog?.selectDirectory;
  if (!picker) return null;
  const selected = await picker(options);
  return selected?.trim() || null;
}
