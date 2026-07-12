// DeviceKit brand mark — the purple phone-in-squircle (plan 27). This is the JSX twin of
// assets/DeviceKitLogo.svg: identical geometry, but the gradient stops read the accent CSS
// ramp (plan 12) so the mark re-tints live when the user changes their accent color.
//
// Two gotchas baked in here:
//  1. Unique gradient id per instance via useId(). Multiple logos render at once (sidebar +
//     login + About). A shared id collides in the DOM and url(#id) resolves to the first
//     match — which can be a hidden 0x0 instance that paints nothing. (ServerKit's lesson.)
//  2. Plan 12 stores accent vars as space-separated "R G B" triplets (for Tailwind alpha),
//     so the stops must be rgb(var(--accent, …)) with a triplet fallback, not a bare hex.
//     We pair --accent (base) with --accent-dim (the darker ramp stop) to reproduce the
//     master asset's light→dark diagonal — DeviceKit's --accent-hover is *brighter* than the
//     base, which would flatten the gradient.
import { useId } from 'react'
import { useBrand } from '../brand'

export default function Logo({ size = 64, className = '' }) {
  const rawId = useId()
  const gradId = `dkBrandGradient-${rawId.replace(/:/g, '')}`
  const fill = `url(#${gradId})`

  // White-label (plan 28): a saved logo data-URI replaces the brand mark everywhere Logo
  // renders (sidebar, login, About). Empty => the default purple-phone SVG below.
  const { logo } = useBrand()
  if (logo) {
    return (
      <img
        src={logo}
        width={size}
        height={size}
        className={className}
        alt="Instance logo"
        style={{ objectFit: 'contain' }}
      />
    )
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 2048 2048"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="DeviceKit logo"
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="rgb(var(--accent, 109 124 255))" />
          <stop offset="100%" stopColor="rgb(var(--accent-dim, 79 70 229))" />
        </linearGradient>
      </defs>
      <rect x="150" y="150" width="1748" height="1748" rx="150" fill="white" />
      <path
        fill={fill}
        fillRule="evenodd"
        d="M378,70 H1670 A308,308 0 0 1 1978,378 V1670 A308,308 0 0 1 1670,1978 H378 A308,308 0 0 1 70,1670 V378 A308,308 0 0 1 378,70 Z M450,220 A230,230 0 0 0 220,450 V1598 A230,230 0 0 0 450,1828 H1598 A230,230 0 0 0 1828,1598 V450 A230,230 0 0 0 1598,220 Z"
      />
      <path
        fill={fill}
        fillRule="evenodd"
        d="M804,434 H1244 A100,100 0 0 1 1344,534 V1514 A100,100 0 0 1 1244,1614 H804 A100,100 0 0 1 704,1514 V534 A100,100 0 0 1 804,434 Z M810,560 A30,30 0 0 0 780,590 V1390 A30,30 0 0 0 810,1420 H1240 A30,30 0 0 0 1270,1390 V590 A30,30 0 0 0 1240,560 Z"
      />
      <rect x="944" y="481" width="160" height="32" rx="16" fill="white" />
      <rect x="924" y="1501" width="200" height="32" rx="16" fill="white" />
      <circle cx="1210" cy="632" r="28" fill="#3ddc97" />
    </svg>
  )
}
