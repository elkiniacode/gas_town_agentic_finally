"use client";

import { useEffect, useState } from "react";
import { formatPrice } from "@/lib/format";

export const FLASH_MS = 500;

type Flash = { dir: "up" | "down"; seq: number } | null;

/**
 * Price text that flashes green/red for ~500 ms whenever the price changes.
 * The span is re-keyed per flash so back-to-back same-direction ticks restart the animation.
 */
export function PriceCell({ price, className = "" }: { price: number | null; className?: string }) {
  const [shown, setShown] = useState(price);
  const [flash, setFlash] = useState<Flash>(null);

  // Detect the change during render (React's "adjust state when a prop changes" pattern).
  if (price !== shown) {
    setShown(price);
    if (shown !== null && price !== null) {
      setFlash({ dir: price > shown ? "up" : "down", seq: (flash?.seq ?? 0) + 1 });
    }
  }

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), FLASH_MS);
    return () => clearTimeout(t);
  }, [flash]);

  return (
    <span
      key={flash?.seq ?? 0}
      data-testid="price"
      className={`rounded px-1 font-mono tabular-nums ${flash ? `flash-${flash.dir}` : ""} ${className}`}
    >
      {formatPrice(price)}
    </span>
  );
}
