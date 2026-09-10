/**
 * index.js — Integration barrel for the Citations adapter.
 *
 * All consumers import from this path only — never a direct relative import.
 *
 * When Netal's real citation-source component lands:
 *   1. Add her component to this directory
 *   2. Change the relevant export line below — one line, zero component edits
 *
 * Current exports:
 *   SourcesUsedList — renders citations as a collapsible "Sources used" section
 *                     inside the thinking block (NOT inline in message text).
 *
 * CitationChip (inline superscripts) has been retired per Day 3-4 revision.
 * contract.js (shape definition) is unchanged.
 */

export { SourcesUsedList } from './SourcesUsedList.jsx'
