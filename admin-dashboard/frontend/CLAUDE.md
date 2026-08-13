# CLAUDE.md

React frontend for the Oliver administrative dashboard. It reads email conversations and semantic matches from the separately deployed admin backend.

## Stack

- React 18
- TypeScript in strict mode
- Vite
- npm

## Conventions

- Source files are TypeScript (`.ts`) or TSX (`.tsx`) only. Do not add JavaScript or JSX files.
- File headers use `// Path:` and `// Description:`.
- Files use kebab-case; React components use PascalCase.
- Every component has an explicit props interface or type.
- API and domain contracts live under `src/lib/models` and are re-exported from `index.ts`.
- API calls stay in typed client modules and use `credentials: "include"`.
- Build API URLs from `VITE_ADMIN_API_URL` (default `/api`) and keep the `/v1` version segment in the typed client.
- Keep business logic and API transformations outside presentational components.
- Write errors inline at the `throw` or return site.
- Do not add automated tests, snapshots, or test-only tooling unless explicitly requested.
- Keep files under 300 lines; extract distinct UI surfaces when a file grows beyond that limit.
- Production Nginx proxies `/api` to the internal admin backend; Vite's local proxy targets its development port.

## Commands

- Install: `npm install`
- Run: `npm run dev`
- Type-check: `npm run typecheck`
- Build: `npm run build`
