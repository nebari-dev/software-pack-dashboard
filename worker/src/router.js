export function resolveTarget(pathname, routes) {
  // Derive the slug from the TRUE first path segment, not the first non-empty
  // one. Using the first non-empty segment (e.g. via filter(Boolean)) would
  // mis-slice `rest` for inputs like `//llm-serving-pack/x` and could let a
  // protocol-relative path (`//evil.com/x`) escape the route map.
  const seg = pathname.split('/')[1];
  // Collapse leading slashes to exactly one so a protocol-relative `rest`
  // (e.g. `//evil.com/x`) can never override the host in `new URL(rest, host)`.
  const normalize = (rest) => '/' + rest.replace(/^\/+/, '');
  if (seg && Object.prototype.hasOwnProperty.call(routes, seg) && seg !== '__default__') {
    const rest = pathname.slice(('/' + seg).length) || '/';
    return { host: routes[seg], rest: normalize(rest) };
  }
  return { host: routes.__default__, rest: normalize(pathname) };
}
