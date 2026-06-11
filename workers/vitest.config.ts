import { defineWorkersConfig, readD1Migrations } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig(async () => ({
  test: {
    setupFiles: ["./test/setup.ts"],
    provide: {
      d1Migrations: await readD1Migrations("./migrations")
    },
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" }
      }
    }
  }
}));
