import { applyD1Migrations, env } from "cloudflare:test";
import { beforeAll, inject } from "vitest";
import type { D1Migration } from "@cloudflare/vitest-pool-workers/config";

const migrations = inject("d1Migrations") as D1Migration[];

beforeAll(async () => {
  await applyD1Migrations(env.LICENSE_DB, migrations);
});
