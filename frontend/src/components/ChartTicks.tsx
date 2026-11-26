/**
 * Category-axis tick for recharts that wraps its label onto up to `maxLines` lines, so every bar keeps its label
 * when the axis uses `interval={0}` (no automatic tick thinning) at narrow widths.
 */

interface WrappedTickProps {
  x?: number
  y?: number
  payload?: { value?: string | number }
  maxChars?: number
  maxLines?: number
  fontSize?: number
  fill?: string
  fontWeight?: number | string
}

export function wrapLabel(text: string, maxChars: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    if (!cur) cur = w
    else if ((cur + ' ' + w).length <= maxChars) cur += ' ' + w
    else {
      lines.push(cur)
      cur = w
    }
  }
  if (cur) lines.push(cur)
  if (lines.length <= maxLines) return lines
  // keep every word: fold the overflow into the last line
  return [...lines.slice(0, maxLines - 1), lines.slice(maxLines - 1).join(' ')]
}

export function WrappedAxisTick({
  x = 0,
  y = 0,
  payload,
  maxChars = 14,
  maxLines = 2,
  fontSize = 10,
  fill = '#334155',
  fontWeight = 600,
}: WrappedTickProps) {
  const lines = wrapLabel(String(payload?.value ?? ''), maxChars, maxLines)
  return (
    <g transform={`translate(${x},${y})`}>
      <text textAnchor="middle" fontSize={fontSize} fill={fill} fontWeight={fontWeight}>
        {lines.map((line, i) => (
          <tspan key={i} x={0} dy={i === 0 ? fontSize + 2 : fontSize + 1}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  )
}
