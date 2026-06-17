import type { ReactNode, Ref } from "react";
import { SwitchControl } from "../SwitchControl";
import { Collapse } from "./Collapse";

interface SwitchDisclosureProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  children: ReactNode;
  size?: "sm" | "md";
  disabled?: boolean;
  "aria-label"?: string;
  className?: string;
  ref?: Ref<HTMLDivElement>;
}

export function SwitchDisclosure({
  checked,
  onChange,
  label,
  children,
  size = "sm",
  disabled = false,
  "aria-label": ariaLabel,
  className,
  ref,
}: SwitchDisclosureProps) {
  return (
    <div ref={ref} className={className}>
      <div
        className="inline-flex items-center gap-1.5 px-1 select-none cursor-pointer"
        onClick={(e) => {
          if ((e.target as HTMLElement).closest("button")) return;
          if (!disabled) onChange(!checked);
        }}
      >
        <SwitchControl
          size={size}
          checked={checked}
          onChange={onChange}
          disabled={disabled}
          aria-label={ariaLabel ?? label}
        />
        <span className="text-sm text-muted">{label}</span>
      </div>
      <Collapse open={checked}>
        <div className="pt-2 pl-[38px]">{children}</div>
      </Collapse>
    </div>
  );
}
