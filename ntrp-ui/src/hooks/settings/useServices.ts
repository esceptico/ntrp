import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { ServiceInfo } from "../../api/client.js";
import { getServices, connectService, disconnectService } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";

export interface UseServicesResult {
  services: ServiceInfo[];
  servicesIndex: number;
  setServicesIndex: React.Dispatch<React.SetStateAction<number>>;
  editingService: boolean;
  serviceKeyValue: string;
  serviceKeyCursor: number;
  serviceSaving: boolean;
  serviceError: string | null;
  serviceConfirmDisconnect: boolean;
  setEditingService: React.Dispatch<React.SetStateAction<boolean>>;
  setServiceKeyValue: React.Dispatch<React.SetStateAction<string>>;
  setServiceKeyCursor: React.Dispatch<React.SetStateAction<number>>;
  setServiceError: React.Dispatch<React.SetStateAction<string | null>>;
  setServiceConfirmDisconnect: React.Dispatch<React.SetStateAction<boolean>>;
  handleSaveServiceKey: () => Promise<void>;
  handleDisconnectService: () => Promise<void>;
  handleServiceKeyInput: (key: Key) => boolean;
  refreshServices: () => void;
}

export function useServices(config: Config): UseServicesResult {
  const [servicesIndex, setServicesIndex] = useState(0);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [editingService, setEditingService] = useState(false);
  const [serviceKeyValue, setServiceKeyValue] = useState("");
  const [serviceKeyCursor, setServiceKeyCursor] = useState(0);
  const [serviceSaving, setServiceSaving] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [serviceConfirmDisconnect, setServiceConfirmDisconnect] = useState(false);

  const { handleKey: handleServiceKeyInput } = useTextInput({
    text: serviceKeyValue,
    cursorPos: serviceKeyCursor,
    setText: setServiceKeyValue,
    setCursorPos: setServiceKeyCursor,
  });

  const refreshServices = useCallback(() => {
    getServices(config).then(r => setServices(r.services)).catch(() => {});
  }, [config]);

  const handleSaveServiceKey = useCallback(async () => {
    if (serviceSaving) return;
    const key = serviceKeyValue.trim();
    const service = services[servicesIndex];
    if (!key || !service) return;

    setServiceSaving(true);
    setServiceError(null);
    try {
      await connectService(config, service.id, key);
      refreshServices();
      setEditingService(false);
      setServiceKeyValue("");
      setServiceKeyCursor(0);
    } catch (e) {
      setServiceError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setServiceSaving(false);
    }
  }, [serviceSaving, serviceKeyValue, services, servicesIndex, config, refreshServices]);

  const handleDisconnectService = useCallback(async () => {
    if (serviceSaving) return;
    const service = services[servicesIndex];
    if (!service) return;
    setServiceSaving(true);
    setServiceError(null);
    try {
      await disconnectService(config, service.id);
      refreshServices();
    } catch (e) {
      setServiceError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setServiceSaving(false);
      setServiceConfirmDisconnect(false);
    }
  }, [serviceSaving, services, servicesIndex, config, refreshServices]);

  return {
    services,
    servicesIndex,
    setServicesIndex,
    editingService,
    serviceKeyValue,
    serviceKeyCursor,
    serviceSaving,
    serviceError,
    serviceConfirmDisconnect,
    setEditingService,
    setServiceKeyValue,
    setServiceKeyCursor,
    setServiceError,
    setServiceConfirmDisconnect,
    handleSaveServiceKey,
    handleDisconnectService,
    handleServiceKeyInput,
    refreshServices,
  };
}
