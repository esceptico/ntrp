import type { ReactNode } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";

export function ErrorPill({ message }: { message: string }) {
  return (
    <Badge tone="bad" size="md" shape="rounded" outline title={message} className="mr-auto max-w-[60%] truncate">
      {message}
    </Badge>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <Badge tone={tone} size="md" shape="rounded" outline>
      {children}
    </Badge>
  );
}
