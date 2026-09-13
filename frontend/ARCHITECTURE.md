# Frontend structure

The frontend keeps HTTP concerns in `src/services` and page rendering in `src/components`.

- `services/client.ts`: shared Axios transport client.
- `services/operations.ts`: health, account, deployment, snapshot, command, and diagnostics APIs.
- `services/errors.ts`: shared API error normalization.
- `services/research.ts`: market data, screener, backtest, and portfolio API calls.
- `services/api.ts`: backward-compatible facade for consumers that still use the old import path.
- `contracts/operations.ts`: shared operations response contracts.
- `contracts/research.ts`: shared market, screener, backtest, and portfolio response contracts.
- `hooks/i18n-context.ts`: translation data and context definition.
- `hooks/I18nContext.tsx`: provider component.
- `hooks/useI18n.ts`: context access hook.
- `App.tsx`: navigation shell and lazy page loading. Individual pages are loaded with `React.lazy` so research and chart dependencies do not inflate the initial bundle.

Components may call service modules and render their results. Service modules do not import components or application state. New API groups should be added to a focused service module and re-exported from `services/api.ts` only when compatibility requires it.
