// SPEC §11.2: a README's relative links are shown as repo paths. Resolves
// `href` against the README's folder; null for in-page anchors. Absolute
// URLs pass through.
export const repoPathFor = (
  readmePath: string,
  href: string,
): string | null => {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return href;
  const target = href.split(/[?#]/, 1)[0];
  if (target === '') return null;
  const parts = target.startsWith('/')
    ? []
    : readmePath.split('/').slice(0, -1);
  for (const part of target.split('/')) {
    if (part === '' || part === '.') continue;
    if (part === '..') parts.pop();
    else parts.push(part);
  }
  return parts.join('/');
};
