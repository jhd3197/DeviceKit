// devicekit-sdk — the stable, versioned surface extension frontends import instead of
// reaching into host internals (plan 04). Resolved via the `devicekit-sdk` Vite alias.
//
// Only what is re-exported here is contract: internal restructures of `src/` must never
// break an extension so long as this surface holds. Bump SDK_VERSION on a breaking change;
// it is mirrored by the backend constant `devicekit.mixins.extensions.SDK_VERSION` and the
// two are asserted equal by `backend/tests/test_frontend_contributions.py`.

// Contract version — keep in sync with the backend SDK_VERSION constant.
export const SDK_VERSION = '1.0.0'

// The REST client + SSE subscription helper.
export { api, subscribeToEvents } from '../../api'

// Real-time streaming primitives (plan 18).
export { default as StreamCanvas } from '../../components/StreamCanvas'
export { default as useMjpegStream } from '../../hooks/useMjpegStream'

// Router helpers so extension pages can link/navigate without importing react-router
// directly (host owns the router singleton).
export {
  Link,
  NavLink,
  useNavigate,
  useParams,
  useLocation,
  useSearchParams,
} from 'react-router-dom'
