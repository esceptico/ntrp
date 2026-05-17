export function RowAction({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onMouseDown={(e) => e.stopPropagation()}
      // Wider than the icon (Fitts's law) — vertical space in the row is
      // tight (22px row) so we widen horizontally to expand the hit area
      // without affecting line-height. Icon stays centered.
      className="grid place-items-center w-[26px] h-[22px] rounded-[5px] text-faint hover:text-ink hover:bg-surface-soft/70 transition-colors"
    >
      {icon}
    </button>
  );
}
