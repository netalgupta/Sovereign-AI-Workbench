const http = require('http')
const WebSocket = require('ws')
const fs = require('fs')

http.get('http://127.0.0.1:9222/json', (res) => {
  let data = ''
  res.on('data', d => data += d)
  res.on('end', async () => {
    const tabs = JSON.parse(data)
    const tab = tabs.find(t => t.url && t.url.includes('5173')) || tabs[0]
    const ws = new WebSocket(tab.webSocketDebuggerUrl)
    let id = 1

    const send = (method, params) => new Promise(resolve => {
      const msgId = id++
      const handler = (raw) => {
        const msg = JSON.parse(raw)
        if (msg.id === msgId) {
          ws.off('message', handler)
          resolve(msg.result)
        }
      }
      ws.on('message', handler)
      ws.send(JSON.stringify({ id: msgId, method, params: params || {} }))
    })

    const sleep = ms => new Promise(r => setTimeout(r, ms))

    ws.on('open', async () => {
      await sleep(500)

      // Expand thinking block 1
      await send('Runtime.evaluate', {
        expression: `(function() {
          var btns = Array.from(document.querySelectorAll('button'));
          var tb = btns.find(function(b) { return b.textContent.indexOf('pipeline steps') >= 0; });
          if (tb) tb.click();
          return tb ? 'clicked' : 'not found';
        })()`,
        returnByValue: true
      })
      await sleep(700)

      // Screenshot 1: sources list visible (no passage expanded yet)
      const ss1 = await send('Page.captureScreenshot', {
        format: 'png',
        clip: { x: 295, y: 140, width: 1080, height: 290, scale: 1.5 }
      })
      fs.writeFileSync('sources_list_visible.png', Buffer.from(ss1.data, 'base64'))
      console.log('Saved sources_list_visible.png')

      // Click first source row (HCU_Operations)
      await send('Runtime.evaluate', {
        expression: `(function() {
          var btns = Array.from(document.querySelectorAll('button'));
          var sb = btns.find(function(b) { return b.textContent.indexOf('HCU_Operations') >= 0; });
          if (sb) sb.click();
          return sb ? 'clicked' : 'not found';
        })()`,
        returnByValue: true
      })
      await sleep(700)

      // Screenshot 2: passage expanded
      const ss2 = await send('Page.captureScreenshot', {
        format: 'png',
        clip: { x: 295, y: 140, width: 1080, height: 390, scale: 1.5 }
      })
      fs.writeFileSync('sources_passage_expanded.png', Buffer.from(ss2.data, 'base64'))
      console.log('Saved sources_passage_expanded.png')

      ws.close()
    })
  })
})
