// Resolves the three specifiers a Hermes Desktop plugin may import to small stand-ins, so
// desktop/plugin.js can be loaded and exercised in Node.
const STUBS = {
  '@hermes/plugin-sdk': new URL('./sdk.mjs', import.meta.url).href,
  'react/jsx-runtime': new URL('./jsx-runtime.mjs', import.meta.url).href,
  react: new URL('./jsx-runtime.mjs', import.meta.url).href
}

export async function resolve(specifier, context, next) {
  if (STUBS[specifier]) return { url: STUBS[specifier], shortCircuit: true }
  return next(specifier, context)
}
