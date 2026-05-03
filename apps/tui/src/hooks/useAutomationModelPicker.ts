import { useState, useMemo, useCallback } from "react";

const DEFAULT_MODEL_OPTION = "__default__";

export interface ModelPickerState {
  createModelCustomOption: string | null;
  createModelIndex: number;
  showModelDropdown: boolean;
  createModelOptions: string[];
  selectedModel: string;
  setCreateModelCustomOption: React.Dispatch<React.SetStateAction<string | null>>;
  setCreateModelIndex: React.Dispatch<React.SetStateAction<number>>;
  setShowModelDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  resetModelState: () => void;
}

export function useAutomationModelPicker(availableModels: string[]): ModelPickerState {
  const [createModelCustomOption, setCreateModelCustomOption] = useState<string | null>(null);
  const [createModelIndex, setCreateModelIndex] = useState(0);
  const [showModelDropdown, setShowModelDropdown] = useState(false);

  const createModelOptions = useMemo(() => {
    const base = [DEFAULT_MODEL_OPTION, ...availableModels];
    if (createModelCustomOption && !base.includes(createModelCustomOption)) {
      base.push(createModelCustomOption);
    }
    return base;
  }, [availableModels, createModelCustomOption]);

  const selectedModel = createModelOptions[createModelIndex] === DEFAULT_MODEL_OPTION
    ? ""
    : (createModelOptions[createModelIndex] ?? "");

  const resetModelState = useCallback(() => {
    setCreateModelCustomOption(null);
    setCreateModelIndex(0);
    setShowModelDropdown(false);
  }, []);

  return {
    createModelCustomOption,
    createModelIndex,
    showModelDropdown,
    createModelOptions,
    selectedModel,
    setCreateModelCustomOption,
    setCreateModelIndex,
    setShowModelDropdown,
    resetModelState,
  };
}
