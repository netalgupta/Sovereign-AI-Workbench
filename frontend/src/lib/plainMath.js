/**
 * plainMath.js — LaTeX in a model's answer, turned into readable plain maths.
 *
 * The chat has no maths renderer, and the model writes its working in LaTeX
 * anyway: a unit conversion came back as
 *   "\[ 1450 \, \text{m}^3/\text{hour} = 218885.41 \, \text{barrel/day} \]"
 * and was shown raw -- markdown ate the backslash before "[", leaving
 * "[ 1450 , \text{m}^3/\text{hour} = … ]" on screen. A renderer (KaTeX)
 * would be a new dependency with its own fonts to ship offline; the maths
 * here is working lines and units, which plain text carries fine.
 *
 * Only maths is touched: fenced and inline code pass through unchanged.
 */

const SUPERSCRIPT = { 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹', '-': '⁻' }

const SYMBOLS = [
  [/\\times/g, '×'], [/\\cdot/g, '·'], [/\\div/g, '÷'], [/\\approx/g, '≈'],
  [/\\leq?(?![a-z])/g, '≤'], [/\\geq?(?![a-z])/g, '≥'], [/\\neq?(?![a-z])/g, '≠'],
  [/\\pm/g, '±'], [/\\degree/g, '°'], [/\\circ/g, '°'], [/\\%/g, '%'],
  [/\\rightarrow|\\to(?![a-z])/g, '→'], [/\\Delta/g, 'Δ'], [/\\rho/g, 'ρ'], [/\\mu/g, 'µ'],
  [/\\(?:,|;|:|!|quad|qquad)/g, ' '], [/\\left|\\right/g, ''],
]

function superscript(digits) {
  return [...digits].map((c) => SUPERSCRIPT[c] ?? c).join('')
}

/** One stretch of LaTeX, as plain text. */
export function latexToPlain(math) {
  let s = math
  // Innermost-first, so nested \frac{\text{a}}{b} unwinds.
  for (let i = 0; i < 6; i += 1) {
    const before = s
    s = s.replace(/\\(?:text|mathrm|textbf|mathbf|operatorname|textit)\s*\{([^{}]*)\}/g, '$1')
    s = s.replace(/\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1) / ($2)')
    s = s.replace(/\\sqrt\s*\{([^{}]*)\}/g, '√($1)')
    if (s === before) break
  }
  s = s.replace(/\^\{(-?\d+)\}|\^(-?\d)/g, (_m, a, b) => superscript(a ?? b))
  s = s.replace(/_\{([^{}]*)\}/g, '$1')
  for (const [re, to] of SYMBOLS) s = s.replace(re, to)
  s = s.replace(/\(([^()]+)\) \/ \(([^()]+)\)/g, (_m, a, b) =>
    (/\s/.test(a.trim()) ? `(${a.trim()})` : a.trim()) + ' / ' + (/\s/.test(b.trim()) ? `(${b.trim()})` : b.trim()))
  s = s.replace(/[{}]/g, '')
  return s.replace(/[ \t]{2,}/g, ' ').trim()
}

const MATH = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)/g
const CODE = /(```[\s\S]*?```|`[^`\n]*`)/g

/** A whole markdown answer, with its LaTeX spans made plain and its code left alone. */
export function plainMath(markdown) {
  if (!markdown || !/\\[[(a-zA-Z]|\$\$/.test(markdown)) return markdown
  return markdown
    .split(CODE)
    .map((part, i) => {
      if (i % 2 === 1) return part // a code span or block
      let out = part.replace(MATH, (_m, display, dollars, inline) => {
        const plain = latexToPlain(display ?? dollars ?? inline)
        return display !== undefined || dollars !== undefined ? `\n\n${plain}\n\n` : plain
      })
      // Bare commands outside delimiters: "= 218,885 \text{ bbl/day}".
      if (/\\(?:text|mathrm|frac|times|cdot|approx)\b/.test(out)) {
        out = out.replace(/[^\n]*\\(?:text|mathrm|frac|times|cdot|approx)\b[^\n]*/g, (line) => latexToPlain(line))
      }
      return out
    })
    .join('')
}
