import { describe, it, expect } from 'vitest';
import { resolveTarget } from '../src/router.js';

const routes = {
  __default__: 'https://software-pack-dashboard.pages.dev',
  'llm-serving-pack': 'https://llm-serving-pack.pages.dev',
};

describe('resolveTarget', () => {
  it('routes a known slug and strips its prefix', () => {
    expect(resolveTarget('/llm-serving-pack/install/', routes))
      .toEqual({ host: 'https://llm-serving-pack.pages.dev', rest: '/install/' });
  });
  it('maps a bare slug to root', () => {
    expect(resolveTarget('/llm-serving-pack', routes))
      .toEqual({ host: 'https://llm-serving-pack.pages.dev', rest: '/' });
  });
  it('sends / to the dashboard', () => {
    expect(resolveTarget('/', routes))
      .toEqual({ host: 'https://software-pack-dashboard.pages.dev', rest: '/' });
  });
  it('sends unknown slugs to the dashboard untouched', () => {
    expect(resolveTarget('/nope/x', routes))
      .toEqual({ host: 'https://software-pack-dashboard.pages.dev', rest: '/nope/x' });
  });
});

describe('resolveTarget SSRF / protocol-relative hardening', () => {
  const routeHosts = Object.values(routes).map((h) => new URL(h).origin);

  // Mirrors the URL construction in src/index.js to prove the final fetch
  // target can never leave the route-table hosts.
  function fetchOrigin(pathname) {
    const { host, rest } = resolveTarget(pathname, routes);
    return new URL(rest, host).origin;
  }

  const probes = [
    '//evil.com/x',
    '/llm-serving-pack//evil.com/x',
    '/__default__/x',
    '//llm-serving-pack/x',
  ];

  for (const probe of probes) {
    it(`never escapes the route map for ${probe}`, () => {
      const origin = fetchOrigin(probe);
      expect(origin).not.toBe('https://evil.com');
      expect(routeHosts).toContain(origin);
    });
  }

  it('collapses protocol-relative root path to the default host', () => {
    expect(resolveTarget('//evil.com/x', routes))
      .toEqual({ host: 'https://software-pack-dashboard.pages.dev', rest: '/evil.com/x' });
  });

  it('collapses protocol-relative subpath under a known slug', () => {
    expect(resolveTarget('/llm-serving-pack//evil.com/x', routes))
      .toEqual({ host: 'https://llm-serving-pack.pages.dev', rest: '/evil.com/x' });
  });

  it('treats __default__ as a non-slug and routes to the default host', () => {
    expect(resolveTarget('/__default__/x', routes))
      .toEqual({ host: 'https://software-pack-dashboard.pages.dev', rest: '/__default__/x' });
  });

  it('regression: normal known-slug subpath still routes correctly', () => {
    expect(resolveTarget('/llm-serving-pack/install/', routes))
      .toEqual({ host: 'https://llm-serving-pack.pages.dev', rest: '/install/' });
  });
});
