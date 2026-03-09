import type { ServiceInfo } from "../../../../api/client.js";
import type { UseCredentialSectionResult } from "../../../../hooks/settings/useCredentialSection.js";
import { CredentialSection } from "./CredentialSection.js";

interface ServicesSectionProps {
  services: UseCredentialSectionResult<ServiceInfo>;
  accent: string;
}

export function ServicesSection({ services, accent }: ServicesSectionProps) {
  return <CredentialSection state={services} accent={accent} />;
}
