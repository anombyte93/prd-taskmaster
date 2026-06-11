import type { Env } from "../src/types";
import type { D1Migration } from "@cloudflare/vitest-pool-workers/config";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

declare module "vitest" {
  export interface ProvidedContext {
    d1Migrations: D1Migration[];
  }
}
