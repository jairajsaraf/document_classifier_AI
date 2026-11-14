// Static export served by FastAPI (https://nextjs.org/docs/app/guides/static-exports).
// trailingSlash emits /document/index.html, which Starlette's StaticFiles(html=True) serves.
export default {
  output: 'export',
  trailingSlash: true,
}
