import { spawn } from 'child_process'
import fs from 'fs'
import path from 'path'

const artifactDir = 'C:\\Users\\ADVAY\\.gemini\\antigravity-ide\\brain\\9c2b2f16-151f-4a51-8c3f-7f816baaa423'
const rootDir = 'C:\\SIH\\SIH26117-Sovereign-Workbench'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function run() {
  console.log('Spawning Edge headless browser for Plan DAG capture...')
  const proc = spawn(
    edgePath,
    [
      '--headless=new',
      '--remote-debugging-port=9222',
      '--user-data-dir=C:\\SIH\\SIH26117-Sovereign-Workbench\\.temp_edge_capture_dag',
      '--window-size=1440,900',
      '--hide-scrollbars',
      'http://localhost:5173',
    ],
    { stdio: 'ignore' }
  )

  let wsUrl = null
  for (let i = 0; i < 30; i++) {
    await sleep(500)
    try {
      const res = await fetch('http://127.0.0.1:9222/json/list')
      const targets = await res.json()
      const page = targets.find((t) => t.type === 'page' && t.url.includes('5173'))
      if (page) {
        wsUrl = page.webSocketDebuggerUrl
        break
      }
    } catch (e) {}
  }

  if (!wsUrl) {
    console.error('Could not find 5173 page')
    proc.kill()
    process.exit(1)
  }

  console.log('Connected to debugger:', wsUrl)
  const ws = new WebSocket(wsUrl)
  await new Promise((resolve) => { ws.onopen = resolve })

  let msgId = 1
  const pending = new Map()
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.id && pending.has(data.id)) {
      pending.get(data.id)(data)
      pending.delete(data.id)
    }
  }

  function send(method, params = {}) {
    return new Promise((resolve) => {
      const id = msgId++
      pending.set(id, resolve)
      ws.send(JSON.stringify({ id, method, params }))
    })
  }

  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  })

  await send('Runtime.evaluate', {
    expression: `
      window.__reactErrors = [];
      window.addEventListener('error', function(e) {
        window.__reactErrors.push({ msg: e.message, stack: e.error ? e.error.stack : 'no stack' });
      });
      window.addEventListener('unhandledrejection', function(e) {
        window.__reactErrors.push({ msg: 'promise: ' + e.reason, stack: e.reason ? e.reason.stack : 'no stack' });
      });
    `,
  })

  // 1. Capture Chat Header showing the Compact Progress Strip
  console.log('1. Capturing chat header showing compact progress strip...')
  const headerClip = { x: 260, y: 0, width: 1180, height: 90, scale: 1.5 }
  const headerRes = await send('Page.captureScreenshot', { format: 'png', clip: headerClip })
  const headerBuf = Buffer.from(headerRes.result.data, 'base64')
  fs.writeFileSync(path.join(rootDir, 'chat_header_progress_strip.png'), headerBuf)
  fs.writeFileSync(path.join(artifactDir, 'chat_header_progress_strip.png'), headerBuf)
  console.log('Saved chat_header_progress_strip.png!')

  // Also full workbench view showing the compact strip in context
  const fullChatRes = await send('Page.captureScreenshot', { format: 'png' })
  const fullChatBuf = Buffer.from(fullChatRes.result.data, 'base64')
  fs.writeFileSync(path.join(rootDir, 'workbench_with_dag_strip.png'), fullChatBuf)
  fs.writeFileSync(path.join(artifactDir, 'workbench_with_dag_strip.png'), fullChatBuf)

  // 2. Navigate to Plan DAG via the Header Link (client-side route)
  console.log('2. Clicking Plan DAG link in header...')
  const clickRes = await send('Runtime.evaluate', {
    expression: `(function() {
      var link = document.querySelector('a[href*="/plan/"]');
      if (link) {
        link.click();
        return 'clicked plan link: ' + link.getAttribute('href');
      }
      return 'link not found';
    })()`,
    returnByValue: true,
  })
  console.log('Click result:', clickRes)
  await sleep(2500)

  const curUrl = await send('Runtime.evaluate', {
    expression: 'window.location.href + " | title: " + document.title + " | nodes: " + document.querySelectorAll(".react-flow__node").length',
    returnByValue: true,
  })
  console.log('State after click:', curUrl)

  const errRes = await send('Runtime.evaluate', {
    expression: 'JSON.stringify(window.__reactErrors)',
    returnByValue: true,
  })
  console.log('React Errors caught:', JSON.stringify(errRes, null, 2))

  // Capture full Plan DAG view (Light Mode)
  console.log('3. Capturing full Plan DAG view (Light Mode)...')
  await send('Runtime.evaluate', {
    expression: `
      document.documentElement.dataset.theme = 'light';
      document.documentElement.classList.remove('dark');
    `,
  })
  await sleep(1000)

  const dagLightRes = await send('Page.captureScreenshot', { format: 'png' })
  const dagLightBuf = Buffer.from(dagLightRes.result.data, 'base64')
  fs.writeFileSync(path.join(rootDir, 'plan_dag_fork_view.png'), dagLightBuf)
  fs.writeFileSync(path.join(artifactDir, 'plan_dag_fork_view.png'), dagLightBuf)
  console.log('Saved plan_dag_fork_view.png!')

  // Capture Plan DAG in Dark Mode
  console.log('4. Capturing full Plan DAG view (Dark Mode)...')
  await send('Runtime.evaluate', {
    expression: `
      document.documentElement.dataset.theme = 'dark';
      document.documentElement.classList.add('dark');
    `,
  })
  await sleep(1000)

  const dagDarkRes = await send('Page.captureScreenshot', { format: 'png' })
  const dagDarkBuf = Buffer.from(dagDarkRes.result.data, 'base64')
  fs.writeFileSync(path.join(rootDir, 'plan_dag_fork_dark.png'), dagDarkBuf)
  fs.writeFileSync(path.join(artifactDir, 'plan_dag_fork_dark.png'), dagDarkBuf)
  console.log('Saved plan_dag_fork_dark.png!')

  // Switch back to light mode for interaction test
  await send('Runtime.evaluate', {
    expression: `
      document.documentElement.dataset.theme = 'light';
      document.documentElement.classList.remove('dark');
    `,
  })
  await sleep(500)

  // 5. Test Node Click Navigation: Click Step 4 node (Math) -> jumps to chat trace
  console.log('5. Clicking Step 4 node in the DAG to test chat trace scroll...')
  await send('Runtime.evaluate', {
    expression: `(function() {
      var nodes = Array.from(document.querySelectorAll('.react-flow__node'));
      var mathNode = nodes.find(function(n) { return n.textContent.indexOf('MATH') >= 0; });
      if (mathNode) {
        mathNode.click();
        return 'clicked math node';
      }
      return 'math node not found';
    })()`,
    returnByValue: true
  })
  await sleep(2000)

  const scrolledChatRes = await send('Page.captureScreenshot', { format: 'png' })
  const scrolledChatBuf = Buffer.from(scrolledChatRes.result.data, 'base64')
  fs.writeFileSync(path.join(rootDir, 'chat_node_jump_scrolled.png'), scrolledChatBuf)
  fs.writeFileSync(path.join(artifactDir, 'chat_node_jump_scrolled.png'), scrolledChatBuf)
  console.log('Saved chat_node_jump_scrolled.png!')

  console.log('All Plan DAG screenshots captured successfully!')
  ws.close()
  proc.kill()
  process.exit(0)
}

run().catch((err) => {
  console.error('Error running capture:', err)
  process.exit(1)
})
