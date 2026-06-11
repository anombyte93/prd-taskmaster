import type { Env } from "./types";

const POST_ONLY_ROUTES = new Set([
  "/stripe/webhook",
  "/license/refresh",
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
  async fetch(request): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (POST_ONLY_ROUTES.has(pathname)) {
      if (request.method !== "POST") {
        return methodNotAllowed();
      }
      return notImplemented();
    }

    return new Response("Not Found", { status: 404 });
  }
} satisfies ExportedHandler<Env>;
