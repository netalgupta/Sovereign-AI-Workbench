/**
 * codeFiles.js — the named files in an answer's code blocks.
 *
 * An answer that spans several files (an app plus its config) is offered
 * as one zip. A block is a file when its name is given, in any of the
 * shapes models write:
 *
 *   File: config/app.yaml          (the form the system prompt asks for)
 *   **config/app.yaml**  /  ### config/app.yaml  /  `config/app.yaml`
 *   ```yaml title="config/app.yaml"   or   ```yaml:config/app.yaml
 *
 * Pure: tested in codeFiles.test.js.
 */

// A path with an extension, or one of the well-known names that have none.
const NAME = String.raw`((?:[\w.-]+/)*(?:Dockerfile|Containerfile|Makefile|Procfile|Jenkinsfile|Vagrantfile|Gemfile|\.env(?:\.[\w-]+)?|\.gitignore|\.dockerignore|\.editorconfig|[\w.-]*[\w-]\.[A-Za-z0-9]{1,8}))`
const LABEL_LINE = new RegExp(
  String.raw`^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*|__)?(?:file(?:name)?|path)?\s*:?\s*(?:\*\*|__)?\s*\x60?` +
    NAME + String.raw`\x60?\s*(?:\*\*|__)?\s*:?\s*$`,
  'i',
)
const TITLE_ATTR = new RegExp(String.raw`title=["']?` + NAME, 'i')
const COLON_INFO = new RegExp(String.raw`^[\w+-]+:` + NAME + '$')
const INFO_IS_NAME = new RegExp('^' + NAME + '$')

export function extractCodeFiles(markdown) {
  if (typeof markdown !== 'string' || !markdown.includes('```')) return []
  const lines = markdown.split('\n')
  const files = []
  for (let i = 0; i < lines.length; i++) {
    const open = lines[i].match(/^\s*```(.*)$/)
    if (!open) continue
    const info = open[1].trim()
    let end = i + 1
    while (end < lines.length && !/^\s*```\s*$/.test(lines[end])) end++
    const body = lines.slice(i + 1, end).join('\n')

    let name = null
    const t = info.match(TITLE_ATTR) || info.match(COLON_INFO) || info.match(INFO_IS_NAME)
    if (t) name = t[1]
    if (!name) {
      // the label line directly above (blank lines between are allowed)
      for (let j = i - 1; j >= Math.max(0, i - 3); j--) {
        if (!lines[j].trim()) continue
        const m = lines[j].match(LABEL_LINE)
        if (m) name = m[1]
        break
      }
    }
    if (name) files.push({ name, content: body.endsWith('\n') ? body : body + '\n', lang: info.split(/[\s:]/)[0] || '' })
    i = end
  }
  // the same path twice: the later block is the corrected one
  const byName = new Map()
  files.forEach((f) => byName.set(f.name, f))
  return [...byName.values()]
}
