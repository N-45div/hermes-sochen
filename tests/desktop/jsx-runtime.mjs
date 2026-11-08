// Elements as plain objects; function components are called right away, so a test can read the
// whole rendered tree as text.
export function jsx(type, props) {
  if (typeof type === 'function') return type(props || {})
  return { type, props: props || {} }
}
export const jsxs = jsx
export const Fragment = 'fragment'
export default { jsx, jsxs, Fragment }
