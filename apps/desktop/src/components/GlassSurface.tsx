import { ComponentPropsWithoutRef, forwardRef } from "react";

type GlassVariant = "clear" | "frosted" | "heavy" | "static";
type GlassTone = "auto" | "light" | "dark";
type GlassRadius = "sm" | "md" | "lg" | "pill";

interface GlassSurfaceProps extends ComponentPropsWithoutRef<"div"> {
  variant?: GlassVariant;
  tone?: GlassTone;
  radius?: GlassRadius;
}

export const GlassSurface = forwardRef<HTMLDivElement, GlassSurfaceProps>(
  function GlassSurface(
    {
      variant = "frosted",
      tone = "auto",
      radius = "md",
      className,
      ...props
    },
    ref,
  ) {
    const classes = [
      "glass-surface",
      `glass-${variant}`,
      `glass-radius-${radius}`,
      className,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div
        ref={ref}
        className={classes}
        data-tone={tone === "auto" ? undefined : tone}
        {...props}
      />
    );
  },
);

export default GlassSurface;
