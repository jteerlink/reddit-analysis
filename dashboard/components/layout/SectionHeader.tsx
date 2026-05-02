interface Props {
  eyebrow?: string;
  title: string;
  subtitle?: string;
}

export function SectionHeader({ eyebrow, title, subtitle }: Props) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-500 mb-1">
          {eyebrow}
        </p>
      )}
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
    </div>
  );
}
