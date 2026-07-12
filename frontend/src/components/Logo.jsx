// DeviceKit brand mark — a white phone glyph on a solid accent-filled squircle badge, mirroring
// the ServerKit lockup (plan 27, retinted plan 28). The mark used to sit on a white plate with a
// purple phone, which read as a sticker on the dark sidebar and vanished on a purple background.
// Now the badge itself carries the accent gradient (so it still re-tints live with the user's
// accent, plan 12) and the phone is a flat white glyph cut out of it — legible on any background.
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
      {/* Solid accent squircle badge (fills with the live accent gradient) */}
      <path
        fill={fill}
        d="M598,128 H1450 A470,470 0 0 1 1920,598 V1450 A470,470 0 0 1 1450,1920 H598 A470,470 0 0 1 128,1450 V598 A470,470 0 0 1 598,128 Z"
      />
      {/* White phone glyph: solid body with screen, speaker slot, and home indicator cut out
          (evenodd) so the accent badge shows through as the screen and bezel details. */}
      <path
        fill="white"
        fillRule="evenodd"
        d="M870,520 H1178 A110,110 0 0 1 1288,630 V1418 A110,110 0 0 1 1178,1528 H870 A110,110 0 0 1 760,1418 V630 A110,110 0 0 1 870,520 Z M876,680 H1172 A44,44 0 0 1 1216,724 V1324 A44,44 0 0 1 1172,1368 H876 A44,44 0 0 1 832,1324 V724 A44,44 0 0 1 876,680 Z M978,584 H1070 A14,14 0 0 1 1084,598 A14,14 0 0 1 1070,612 H978 A14,14 0 0 1 964,598 A14,14 0 0 1 978,584 Z M958,1436 H1090 A14,14 0 0 1 1104,1450 A14,14 0 0 1 1090,1464 H958 A14,14 0 0 1 944,1450 A14,14 0 0 1 958,1436 Z"
      />
      {/* Green status LED (family continuity with the Android accent) */}
      <circle cx="1150" cy="740" r="30" fill="#3ddc97" />
    </svg>
  )
}
