const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const formatUsd = (n: number): string => usd.format(n);

export const formatPrice = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : n.toFixed(2);

export const formatPct = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

/** Quantity with up to 4 dp, trailing zeros stripped (10 → "10", 2.5 → "2.5"). */
export const formatQty = (n: number): string => String(Number(n.toFixed(4)));

/** Tailwind text color class for a signed value. */
export const signClass = (n: number | null | undefined): string =>
  !n ? "text-muted" : n > 0 ? "text-up" : "text-down";
