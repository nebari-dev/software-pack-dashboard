import routes from './routes.json';
import { resolveTarget } from './router.js';

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const { host, rest } = resolveTarget(url.pathname, routes);
    const target = new URL(rest + url.search, host);
    // Defense in depth: never fetch a host outside the route table, even if a
    // new path-normalization bypass is discovered later.
    if (target.origin !== new URL(host).origin) {
      return new Response('Bad request', { status: 400 });
    }
    const proxied = new Request(target, request);
    const response = await fetch(proxied);
    // Stream the upstream body through without buffering.
    return new Response(response.body, response);
  },
};
