import type { UseProvidersResult } from "./useProviders.js";
import type { Key } from "../useKeypress.js";

export interface UseApiKeysResult {
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useApiKeys(providers: UseProvidersResult): UseApiKeysResult {
  return {
    handleKeypress: providers.handleKeypress,
    isEditing: providers.isEditing,
    cancelEdit: providers.cancelEdit,
  };
}
