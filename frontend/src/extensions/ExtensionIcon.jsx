import React from 'react'
import { Puzzle } from 'lucide-react'
import { sanitizeSvgInner } from '../utils/sanitizeSvg'

// Render an extension-supplied inline-SVG icon string safely (plan 04). The manifest icon
// is sanitized (scripts / handlers / external refs stripped) and injected into a
// host-controlled <svg> wrapper so it inherits the app's sizing (w-4 h-4) and currentColor
// — extensions can't override stroke color or leak the layout. Falls back to a generic
// puzzle glyph when no icon is provided.
export default function ExtensionIcon({ svg, className = 'w-4 h-4' }) {
  const inner = sanitizeSvgInner(svg)
  if (!inner) return <Puzzle className={className} />
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      dangerouslySetInnerHTML={{ __html: inner }}
    />
  )
}
