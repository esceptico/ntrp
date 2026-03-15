import { useCallback, useState } from "react";
import type { UseProvidersResult } from "./useProviders.js";
import type { UseServicesResult } from "./useServices.js";
import type { Key } from "../useKeypress.js";

export interface UseApiKeysResult {
  activeList: "providers" | "services";
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useApiKeys(
  providers: UseProvidersResult,
  services: UseServicesResult,
): UseApiKeysResult {
  const [activeList, setActiveList] = useState<"providers" | "services">("providers");

  const isEditing = providers.isEditing || services.isEditing;

  const cancelEdit = useCallback(() => {
    if (providers.isEditing) providers.cancelEdit();
    if (services.isEditing) services.cancelEdit();
  }, [providers, services]);

  const handleKeypress = useCallback((key: Key) => {
    if (activeList === "providers") {
      if ((key.name === "down" || key.name === "j") &&
          providers.selectedIndex === providers.items.length - 1 &&
          !providers.isEditing) {
        setActiveList("services");
        return;
      }
      providers.handleKeypress(key);
    } else {
      if ((key.name === "up" || key.name === "k") &&
          services.selectedIndex === 0 &&
          !services.isEditing) {
        setActiveList("providers");
        return;
      }
      services.handleKeypress(key);
    }
  }, [activeList, providers, services]);

  return {
    activeList,
    handleKeypress,
    isEditing,
    cancelEdit,
  };
}
