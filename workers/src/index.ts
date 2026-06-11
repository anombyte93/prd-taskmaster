import type { Env } from "./types";
import { handleLicenseRefresh } from "./refresh";
import { handleStripeWebhook } from "./stripe";

const POST_ONLY_ROUTES = new Set([
  "/stripe/webhook",
  "/telemetry"
]);

function methodNotAllowed(): Response {
  return new Response("Method Not Allowed", {
    status: 405,
    headers: { Allow: "POST" }
  });
}

function notImplemented(): Response {
  return new Response("Not Implemented", { status: 501 });
}

export default {
  async fetch(request, env, ctx): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/license/refresh") {
      return handleLicenseRefresh(request, env);
    }

    if (POST_ONLY_ROUTES.has(pathname)) {
      if (request.method !== "POST") {
        return methodNotAllowed();
      }
      if (pathname === "/stripe/webhook") {
        return handleStripeWebhook(request, env, ctx);
      }
      return notImplemented();
    }

    return new Response("Not Found", { status: 404 });
  }
} satisfies ExportedHandler<Env>;
