export function resolveTarget(pathname, routes) {
  const seg = pathname.split('/').filter(Boolean)[0];
  if (seg && Object.prototype.hasOwnProperty.call(routes, seg) && seg !== '__default__') {
    const rest = pathname.slice(('/' + seg).length) || '/';
    return { host: routes[seg], rest };
  }
  return { host: routes.__default__, rest: pathname };
}
