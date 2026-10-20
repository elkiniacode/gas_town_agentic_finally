"use client";

import { Terminal } from "@/components/Terminal";
import { AppDataProvider } from "@/lib/useAppData";
import { PriceStreamProvider } from "@/lib/usePriceStream";

export default function Home() {
  return (
    <PriceStreamProvider>
      <AppDataProvider>
        <Terminal />
      </AppDataProvider>
    </PriceStreamProvider>
  );
}
