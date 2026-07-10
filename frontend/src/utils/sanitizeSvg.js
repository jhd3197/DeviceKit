// sanitizeSvgInner — make an extension-supplied inline SVG string safe to inject with
// dangerouslySetInnerHTML (plan 04, port of ServerKit's sanitizeSvg). Manifest icons are
// authored by extension authors, so we strip anything that could execute or exfiltrate:
// <script>, event handlers (on*), javascript:/data: URLs, <foreignObject>, and external
// references. This is deliberately conservative — icons are simple vector shapes.
//
// Returns a string safe to place inside a host-controlled <svg> wrapper. The caller owns
// the outer <svg> (sizing/color via currentColor); we return only sanitized inner markup.

const DANGEROUS_TAGS = /<\s*(script|foreignObject|iframe|object|embed|style|link|meta|animate|set)\b[^>]*>/gi
const CLOSING_DANGEROUS = /<\s*\/\s*(script|foreignObject|iframe|object|embed|style|link|meta|animate|set)\s*>/gi
// on<event>="..." or on<event>='...'
const EVENT_HANDLERS = /\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi
// href/xlink:href/src pointing at javascript:, data:, or an external URL
const DANGEROUS_URLS = /\s(?:xlink:href|href|src)\s*=\s*("(?:javascript:|data:|https?:|\/\/)[^"]*"|'(?:javascript:|data:|https?:|\/\/)[^']*')/gi

/**
 * Sanitize the inner markup of an extension SVG icon.
 * @param {string} raw - the raw SVG string from a manifest (may include the <svg> wrapper).
 * @returns {string} sanitized inner markup (wrapper stripped), or '' if input is unusable.
 */
export function sanitizeSvgInner(raw) {
  if (!raw || typeof raw !== 'string') return ''

  let s = raw.trim()

  // Strip a leading <svg ...> and trailing </svg> — the host provides its own wrapper so
  // it controls size (w-4 h-4) and color (currentColor). Keep only the paths inside.
  s = s.replace(/^<\s*svg\b[^>]*>/i, '').replace(/<\s*\/\s*svg\s*>\s*$/i, '')

  // Remove dangerous elements and their closing tags.
  s = s.replace(DANGEROUS_TAGS, '').replace(CLOSING_DANGEROUS, '')
  // Strip inline event handlers.
  s = s.replace(EVENT_HANDLERS, '')
  // Strip javascript:/data:/external URL references.
  s = s.replace(DANGEROUS_URLS, '')

  return s.trim()
}

export default sanitizeSvgInner
