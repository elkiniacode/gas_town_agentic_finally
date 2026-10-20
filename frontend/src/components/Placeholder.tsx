import type { ReactNode } from "react";

/** Centered muted body for panels whose real content is built by a later bead. */
export function Placeholder({ owner, children }: { owner: string; children?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 p-4 text-center text-xs text-muted">
      {children}
      <span className="font-mono text-[10px] opacity-60">placeholder · {owner}</span>
    </div>
  );
}
