# CircuitPilot web workspace

Next.js App Router, React, TypeScript, CSS, and model-derived SVG.
Requires Node.js 24, pnpm 11.25.0, and the Python backend on 127.0.0.1:8000.

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

Open http://127.0.0.1:3000. `/api/` is proxied to FastAPI; cookies stay same-origin.
Set `CIRCUITPILOT_API_URL` before starting/building to choose another backend.
Browser tests use real endpoints and an explicitly synthetic calibration image;
they do not measure real-photo detection accuracy. Only completed step numbers keyed
by plan ID are stored locally; account tokens and photos never enter localStorage.
