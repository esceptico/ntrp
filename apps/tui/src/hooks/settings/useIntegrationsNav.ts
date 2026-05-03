import { useCallback, useState } from "react";
import type { UseConnectionsResult } from "./useConnections.js";
import type { UseServicesResult } from "./useServices.js";
import type { Key } from "../useKeypress.js";

export interface UseIntegrationsNavResult {
  activeList: "connections" | "services";
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
  actionInProgress: string | null;
}

export function useIntegrationsNav(
  connections: UseConnectionsResult,
  services: UseServicesResult,
): UseIntegrationsNavResult {
  const [activeList, setActiveList] = useState<"connections" | "services">("connections");

  const isEditing = connections.isEditing || services.isEditing;

  const cancelEdit = useCallback(() => {
    if (connections.isEditing) connections.cancelEdit();
    if (services.isEditing) services.cancelEdit();
  }, [connections, services]);

  const handleKeypress = useCallback((key: Key) => {
    if (activeList === "connections") {
      const atLastConnection = connections.sourceItem === "web";
      if ((key.name === "down" || key.name === "j") && atLastConnection && !connections.isEditing) {
        setActiveList("services");
        return;
      }
      connections.handleKeypress(key);
    } else {
      if ((key.name === "up" || key.name === "k") &&
          services.selectedIndex === 0 &&
          !services.isEditing) {
        setActiveList("connections");
        return;
      }
      services.handleKeypress(key);
    }
  }, [activeList, connections, services]);

  return {
    activeList,
    handleKeypress,
    isEditing,
    cancelEdit,
    actionInProgress: connections.actionInProgress,
  };
}
