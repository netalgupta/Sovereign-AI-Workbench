/* Setup wizard: five screens, driven by real results from the main process. */
(function () {
  const $ = (id) => document.getElementById(id)
  const api = window.sovereign
  const ORDER = ['welcome', 'machine', 'location', 'install', 'finish']
  const STEPS = [
    ['verify', 'Checking the package'],
    ['python', 'Python and its packages'],
    ['ollama', 'Ollama and the models'],
    ['app', 'The workbench'],
    ['shell', 'The desktop app'],
    ['settings', 'Settings and shortcut'],
    ['index', 'Building the search index'],
  ]
  let info = null
  let installDir = ''
  let started = 0
  let timer = null
  const results = {}

  const gb = (b) => (b == null ? '—' : b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`)
  const text = (el, s) => { el.textContent = s }

  function show(screen) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('on', s.id === screen))
    const idx = ORDER.indexOf(screen)
    document.querySelectorAll('#steps li').forEach((li) => {
      const i = ORDER.indexOf(li.dataset.screen)
      li.classList.toggle('on', i === idx)
      li.classList.toggle('done', i < idx)
    })
  }
  document.querySelectorAll('[data-go]').forEach((b) => b.addEventListener('click', () => show(b.dataset.go)))

  // ── welcome: what the package holds ──
  const LABELS = { python: ['Python and packages', 'Installed offline from the wheelhouse'], ollama: ['Ollama and models', 'Local model server and the registered models'], app: ['The workbench', 'Backend, interface, model caches, corpora'] }
  function renderPackage() {
    const rows = $('package-rows')
    rows.innerHTML = ''
    if (!info.manifest) {
      rows.innerHTML = '<div class="prow"><div><b>No package found</b><div class="sub">Setup looks for a folder named payload next to this program. Run it from the drive it came on.</div></div></div>'
      return
    }
    for (const c of info.manifest.components) {
      const [title, sub] = LABELS[c.id] || [c.id, '']
      const extra = c.id === 'ollama' && c.models ? ` · ${c.models.join(', ')}` : c.id === 'python' && c.distributions ? ` · ${c.distributions} pinned packages` : ''
      const row = document.createElement('div')
      row.className = 'prow'
      row.innerHTML = `<div><b></b><div class="sub"></div></div><div class="size"></div>`
      text(row.querySelector('b'), title)
      text(row.querySelector('.sub'), sub + extra)
      text(row.querySelector('.size'), gb(c.bytes))
      rows.appendChild(row)
    }
    $('start-btn').disabled = false
  }

  // ── machine ──
  function card(k, v, s, tone) {
    const el = document.createElement('div')
    el.className = `card ${tone || ''}`
    el.innerHTML = '<div class="k"></div><div class="v"></div><div class="s"></div>'
    text(el.querySelector('.k'), k)
    text(el.querySelector('.v'), v)
    text(el.querySelector('.s'), s || '')
    return el
  }
  function renderMachine() {
    const m = info.machine
    const box = $('machine-cards')
    box.innerHTML = ''
    const gpu = m.gpus[0]
    box.appendChild(gpu
      ? card('GPU', gpu.name, `${gpu.vramGB} GB video memory · driver ${gpu.driver}`, gpu.vramGB >= 8 ? 'ok' : 'warn')
      : card('GPU', 'No NVIDIA GPU found', 'Models will run on the CPU, much more slowly', 'warn'))
    box.appendChild(card('Memory', `${m.ramGB} GB`, m.ramGB >= 16 ? 'Enough for the workbench' : '16 GB or more recommended', m.ramGB >= 16 ? 'ok' : 'warn'))
    box.appendChild(card('Processor', m.cpu, `${m.cores} threads`))
    box.appendChild(card('Ollama', m.ollamaInstalled ? 'Already installed' : 'Will be installed', 'The local model server', m.ollamaInstalled ? 'ok' : ''))
    box.appendChild(card('Docker', m.dockerRunning ? 'Running' : 'Not running', m.dockerRunning ? 'Generated code runs in its isolated sandbox' : 'Needed only to RUN generated code; everything else works without it', m.dockerRunning ? 'ok' : 'warn'))
    box.appendChild(card('System', m.os, ''))
    const notes = []
    if (!gpu) notes.push('No NVIDIA GPU was found. The workbench will install and run, but answers will be slow.')
    if (!m.dockerRunning) notes.push('Docker Desktop is not running. Code can be written but not executed until it is.')
    $('machine-note').hidden = notes.length === 0
    text($('machine-note'), notes.join(' '))
  }

  // ── location ──
  async function renderSpace() {
    text($('dir'), installDir)
    const free = await api.freeBytes(installDir)
    const need = (info.manifest?.components || []).reduce((n, c) => n + (c.bytes || 0), 0)
    const ok = free == null || free > need * 1.1
    $('space').innerHTML = `Needs about <b>${gb(need)}</b> · <span class="${ok ? '' : 'bad'}">${gb(free)} free on this drive</span>`
    $('install-btn').disabled = !ok || !info.manifest
  }
  $('choose').addEventListener('click', async () => {
    const res = await api.chooseDir(installDir)
    if (res) {
      installDir = res.dir.endsWith('SovereignWorkbench') ? res.dir : `${res.dir}\\SovereignWorkbench`
      renderSpace()
    }
  })

  // ── install ──
  function renderComponents() {
    const box = $('components')
    box.innerHTML = ''
    for (const [id, title] of STEPS) {
      const el = document.createElement('div')
      el.className = 'comp'
      el.id = `c-${id}`
      el.innerHTML = '<div class="comp-top"><span class="icon"></span><span class="comp-title"></span><span class="comp-meta"></span></div><div class="bar indeterminate"><i></i></div><div class="comp-detail muted">Waiting</div>'
      text(el.querySelector('.comp-title'), title)
      box.appendChild(el)
    }
  }
  api.onProgress((msg) => {
    const el = $(`c-${msg.step}`)
    if (!el) return
    const meta = el.querySelector('.comp-meta')
    const detail = el.querySelector('.comp-detail')
    const bar = el.querySelector('.bar')
    if (msg.status) {
      el.classList.remove('running', 'done', 'failed')
      el.classList.add(msg.status)
      const icon = el.querySelector('.icon')
      icon.textContent = msg.status === 'done' ? '✓' : msg.status === 'failed' ? '!' : ''
      if (msg.status === 'running') text(detail, 'Starting…')
      if (msg.status === 'done') {
        text(detail, msg.summary || 'Done')
        text(meta, `${msg.seconds}s`)
        results[msg.step] = msg.summary
      }
      if (msg.status === 'failed') {
        text(detail, msg.error)
        text(meta, `${msg.seconds}s`)
      }
    }
    if (msg.total) {
      bar.classList.remove('indeterminate')
      bar.querySelector('i').style.width = `${Math.min(100, (100 * msg.done) / msg.total).toFixed(1)}%`
      text(meta, msg.unit === 'bytes' ? `${gb(msg.done)} / ${gb(msg.total)}` : `${msg.done} / ${msg.total} ${msg.unit || ''}`)
    } else if (msg.unit === 'lines') {
      bar.classList.add('indeterminate')
    }
    if (msg.detail && !msg.status) text(detail, msg.detail)
  })
  let logLines = 0
  api.onLog((line) => {
    const pre = $('log')
    pre.textContent += line + '\n'
    logLines += 1
    text($('log-count'), `(${logLines} lines)`)
    if (pre.textContent.length > 200000) pre.textContent = pre.textContent.slice(-150000)
    pre.scrollTop = pre.scrollHeight
  })

  async function runInstall() {
    show('install')
    renderComponents()
    $('retry-btn').hidden = true
    text($('install-title'), 'Installing')
    started = Date.now()
    clearInterval(timer)
    timer = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000)
      text($('elapsed'), `Elapsed ${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`)
    }, 1000)
    try {
      await api.install(installDir)
      clearInterval(timer)
      renderSummary()
      show('finish')
    } catch (err) {
      clearInterval(timer)
      text($('install-title'), 'Setup stopped')
      text($('install-lede'), `${String(err.message || err).replace(/^Error invoking remote method 'setup:run': Error: /, '')} Fix that and try again: finished steps are kept, so setup continues where it stopped.`)
      $('retry-btn').hidden = false
      $('log-box').open = true
    }
  }
  $('install-btn').addEventListener('click', runInstall)
  $('retry-btn').addEventListener('click', runInstall)

  // ── finish ──
  function renderSummary() {
    const ul = $('summary')
    ul.innerHTML = ''
    for (const [id, title] of STEPS) {
      const li = document.createElement('li')
      li.innerHTML = '<span class="ok">✓</span><span class="t"></span><span class="d"></span>'
      text(li.querySelector('.t'), title)
      text(li.querySelector('.d'), results[id] || '')
      ul.appendChild(li)
    }
    text($('finish-lede'), `Installed to ${installDir}. Every component is on this machine; the drive can be removed. A shortcut is on the desktop.`)
  }
  $('launch-btn').addEventListener('click', () => api.launch())
  $('open-logs').addEventListener('click', () => api.openLogFolder())

  // ── boot ──
  api.info().then((i) => {
    info = i
    installDir = i.defaultDir
    renderPackage()
    renderMachine()
    renderSpace()
  })
})()
