import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      include: ["src/**/*.test.{ts,tsx}"],
      restoreMocks: true,
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        // Generated shadcn primitives and the entry point aren't ours to unit-test.
        exclude: ["src/components/ui/**", "src/main.tsx", "src/**/*.test.{ts,tsx}", "src/test/**"],
        reporter: ["text-summary", "text"],
        // Guard the logic that's unit-tested; page components are covered by end-to-end runs.
        thresholds: {
          "src/money.ts": { lines: 85, branches: 85 },
          "src/api/client.ts": { lines: 90, branches: 80 },
          "src/api/useRoomSocket.ts": { lines: 90, branches: 75 },
          "src/components/TurnTimer.tsx": { lines: 90, branches: 80 },
        },
      },
    },
  }),
);
