/**
 * contract.js — Calculation Trace Viewer shape contract for the integration boundary.
 *
 * Owner: Kanishka (CARD 08 / FRONTEND.md §3.8)
 *
 * Real CalcTraceCard component MUST accept exactly this shape:
 * {
 *   expression: string,       // The mathematical or engineering equation
 *   steps: CalcStep[],        // Step-by-step simplification trace from CARD 08
 *   finalResult: string,      // The verified result (e.g. "115.0%")
 *   isVerified: boolean,      // Must be true to show "✓ verified by SymPy" badge (NFR-5 visual proof)
 *   timestamp?: string,
 *   unit?: string,
 *   variables?: Record<string, number | string>,
 * }
 *
 * Exact badge requirement (NFR-5):
 * Must show verbatim: "✓ verified by SymPy" in monospace or badge styling.
 *
 * @typedef {Object} CalcStep
 * @property {number} stepNumber - Sequential index 1, 2, 3...
 * @property {string} description - Step explanation (e.g. "Substitute base capacity into heat balance equation")
 * @property {string} intermediateFormula - Intermediate equation
 * @property {string} result - Step intermediate result
 *
 * @typedef {Object} CalcTraceProps
 * @property {string} expression - Primary math formula
 * @property {CalcStep[]} steps - Step-by-step derivation steps
 * @property {string} finalResult - Final calculated value
 * @property {boolean} isVerified - Whether SymPy verification succeeded
 * @property {string} [timestamp] - Calculation timestamp
 * @property {string} [unit] - Engineering unit
 * @property {Record<string, number|string>} [variables] - Input variables map
 */

/**
 * Lightweight runtime validation for CalcTraceCard props.
 * @param {any} props
 * @returns {boolean}
 */
export function validateProps(props) {
  if (!props) {
    console.warn('[Integration: calc-trace] Missing props: CalcTraceCard requires props object.')
    return false
  }
  const missing = []
  if (!props.expression) missing.push('expression')
  if (!props.steps || !Array.isArray(props.steps)) missing.push('steps (Array)')
  if (props.finalResult === undefined) missing.push('finalResult')
  if (props.isVerified === undefined) missing.push('isVerified (boolean)')

  if (missing.length > 0) {
    console.warn(
      `[Integration: calc-trace] Contract violation in CalcTraceCard: missing required field(s): ${missing.join(
        ', '
      )}. Required shape: { expression, steps, finalResult, isVerified }`,
      props
    )
    return false
  }
  return true
}

export const CANONICAL_CALC_TRACE = {
  expression: 'Delta_T_bed = (Q_rxn * Feed_Rate) / (m_dot * C_p)',
  steps: [
    {
      stepNumber: 1,
      description: 'Fetch current fresh feed rate and heat of reaction constants',
      intermediateFormula: 'Q_rxn = 418.4 kJ/mol, Feed_Rate = 115.0%',
      result: '48.118 MW heat release',
    },
    {
      stepNumber: 2,
      description: 'Evaluate adiabatic temperature rise against hydrogen quench limit',
      intermediateFormula: 'Delta_T = 48.118 MW / (120 kg/s * 2.8 kJ/kg*K)',
      result: '143.2°C temperature delta',
    },
    {
      stepNumber: 3,
      description: 'Verify maximum peak bed temperature does not breach 435.0°C interlock',
      intermediateFormula: 'T_bed_peak = 280.0°C + 143.2°C = 423.2°C < 435.0°C',
      result: '11.8°C safety margin',
    },
  ],
  finalResult: '423.2°C (11.8°C margin)',
  isVerified: true,
  timestamp: '2026-09-10 14:23:05',
  unit: '°C',
  variables: {
    Feed_Rate: '115%',
    Quench_Rate: '24.2 Nm³/m³',
    Base_T: '280°C',
  },
}
