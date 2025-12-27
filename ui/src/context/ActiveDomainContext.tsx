import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import { getActiveDomain, setActiveDomain as storeActiveDomain } from "../api/client";

type ActiveDomainState = {
  domain: string;
  setDomain: (domain: string) => void;
};

const ActiveDomainContext = createContext<ActiveDomainState | undefined>(undefined);

export function ActiveDomainProvider({ children }: { children: ReactNode }) {
  const [domain, setDomainState] = useState<string>(getActiveDomain());

  const setDomain = (next: string) => {
    storeActiveDomain(next);
    setDomainState(next);
  };

  const value = useMemo(() => ({ domain, setDomain }), [domain]);

  return <ActiveDomainContext.Provider value={value}>{children}</ActiveDomainContext.Provider>;
}

export function useActiveDomain() {
  const ctx = useContext(ActiveDomainContext);
  if (!ctx) {
    throw new Error("useActiveDomain must be used within an ActiveDomainProvider");
  }
  return ctx;
}
