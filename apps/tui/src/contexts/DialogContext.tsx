import React, { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface DialogContextValue {
  open: (element: ReactNode) => void;
  close: () => void;
  isOpen: boolean;
}

const DialogContext = createContext<DialogContextValue | null>(null);

export function DialogProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<ReactNode>(null);

  const open = useCallback((element: ReactNode) => setCurrent(element), []);
  const close = useCallback(() => setCurrent(null), []);

  return (
    <DialogContext.Provider value={{ open, close, isOpen: current !== null }}>
      {children}
      {current}
    </DialogContext.Provider>
  );
}

export function useDialog(): DialogContextValue {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialog must be used within DialogProvider");
  return ctx;
}
