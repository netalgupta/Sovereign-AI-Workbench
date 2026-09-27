/**
 * motion.js — Sovereign Spatial Motion System
 *
 * Coherent physical motion tokens and variants across the workbench.
 * Built on framer-motion springs. No arbitrary CSS transitions.
 *
 * Core principles:
 * - "Move object, not display component"
 * - Objects lift with subtle depth before moving
 * - Origin-aware expansion and contraction
 * - Restrained, non-distracting spring physics
 */

export const springs = {
  // Ultra-responsive for small interactive controls, buttons, chips
  micro: {
    type: 'spring',
    stiffness: 500,
    damping: 35,
    mass: 0.8,
  },
  // Tactile feedback for card presses and list items
  tactile: {
    type: 'spring',
    stiffness: 420,
    damping: 30,
    mass: 0.9,
  },
  // Spatial transitions: panels, drawers, modals, workspace tiles
  spatial: {
    type: 'spring',
    stiffness: 340,
    damping: 32,
    mass: 1,
  },
  // Gentle reflow for text, expanding accordions, citation inline cards
  editorial: {
    type: 'spring',
    stiffness: 280,
    damping: 28,
    mass: 1.1,
  },
  // Slow, serene camera or large graph transitions
  serene: {
    type: 'spring',
    stiffness: 180,
    damping: 26,
    mass: 1.2,
  },
}

export const transitions = {
  instant: { duration: 0.12, ease: [0.16, 1, 0.3, 1] },
  fast: { duration: 0.18, ease: [0.16, 1, 0.3, 1] },
  base: { duration: 0.26, ease: [0.16, 1, 0.3, 1] },
  slow: { duration: 0.4, ease: [0.16, 1, 0.3, 1] },
}

/**
 * Workspace panel variants: supports normal, minimized, focused, and drag-lifted
 */
export const workspacePanelVariants = {
  initial: {
    opacity: 0,
    scale: 0.96,
    y: 8,
  },
  animate: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: springs.spatial,
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    y: 6,
    transition: transitions.fast,
  },
  minimized: {
    opacity: 0.9,
    scale: 0.98,
    transition: springs.editorial,
  },
  focus: {
    opacity: 1,
    scale: 1,
    transition: springs.spatial,
  },
}

/**
 * Dropdown / popover origin reveal
 */
export const popoverVariants = {
  closed: {
    opacity: 0,
    scale: 0.95,
    y: -4,
    transformOrigin: 'top center',
    transition: transitions.fast,
  },
  open: {
    opacity: 1,
    scale: 1,
    y: 0,
    transformOrigin: 'top center',
    transition: springs.micro,
  },
}

/**
 * Inline citation evidence drawer expansion (smooth height reflow)
 */
export const citationAccordionVariants = {
  collapsed: {
    opacity: 0,
    height: 0,
    marginTop: 0,
    marginBottom: 0,
    transition: {
      height: { duration: 0.22, ease: [0.16, 1, 0.3, 1] },
      opacity: { duration: 0.15 },
    },
  },
  expanded: {
    opacity: 1,
    height: 'auto',
    marginTop: 8,
    marginBottom: 8,
    transition: {
      height: { duration: 0.26, ease: [0.16, 1, 0.3, 1] },
      opacity: { duration: 0.2, delay: 0.05 },
    },
  },
}

/**
 * Reusable tactile microinteractions
 */
export const buttonTapMotion = {
  whileHover: { scale: 1.015, y: -0.5 },
  whileTap: { scale: 0.975, y: 0.5 },
  transition: springs.micro,
}

export const cardHoverMotion = {
  whileHover: { y: -2, transition: springs.micro },
  transition: springs.tactile,
}

export const iconButtonTapMotion = {
  whileHover: { scale: 1.08 },
  whileTap: { scale: 0.92 },
  transition: springs.micro,
}
