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
