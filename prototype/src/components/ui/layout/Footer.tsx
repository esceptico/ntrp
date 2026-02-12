import React from "react";
import { colors } from "../colors.js";

interface FooterProps {
  children: React.ReactNode;
  right?: React.ReactNode;
}

export function Footer({ children, right }: FooterProps) {
  return (
    <box marginTop={1} justifyContent="space-between">
      <text><span fg={colors.footer}>{children}</span></text>
      {right && <text><span fg={colors.footer}>{right}</span></text>}
    </box>
  );
}
