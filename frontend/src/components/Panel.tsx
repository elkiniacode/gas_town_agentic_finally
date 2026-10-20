import type { ReactNode } from "react";

/** Bordered terminal panel with a compact title row. */
export function Panel({
  title,
  actions,
  className = "",
  bodyClassName = "",
  testId,
  children,
}: {
  title: ReactNode;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  testId?: string;
  children: ReactNode;
}) {
  return (
    <section data-testid={testId} className={`flex min-h-0 min-w-0 flex-col rounded border border-border bg-panel ${className}`}>
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-border px-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</h2>
        {actions}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}
