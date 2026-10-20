const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const formatUsd = (n: number): string => usd.format(n);

export const formatPrice = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : n.toFixed(2);

/** Percentage points rounded to 2 dp, with -0 normalized to 0. */
export const roundPct = (n: number): number => Math.round(n * 100) / 100 || 0;

export const formatPct = (n: number | null | undefined): string => {
  if (n === null || n === undefined) return "—";
  const r = roundPct(n);
  return `${r > 0 ? "+" : ""}${r.toFixed(2)}%`;
};

/** Signed dollars: "+$12.30", "-$4.00", "$0.00". */
export const formatSignedUsd = (n: number): string => {
  const r = Math.round(n * 100) / 100 || 0;
  return `${r > 0 ? "+" : ""}${usd.format(r)}`;
};

/** Quantity with up to 4 dp, trailing zeros stripped (10 → "10", 2.5 → "2.5"). */
export const formatQty = (n: number): string => String(Number(n.toFixed(4)));

/** Tailwind text color class for a signed value. */
export const signClass = (n: number | null | undefined): string =>
  !n ? "text-muted" : n > 0 ? "text-up" : "text-down";
