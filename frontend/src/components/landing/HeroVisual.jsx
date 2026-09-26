import { useRef } from 'react'

const structures = [
  { left: '8%', width: '8%', height: '37%', delay: '0s' },
  { left: '20%', width: '11%', height: '59%', delay: '-1s' },
  { left: '37%', width: '7%', height: '43%', delay: '-2.4s' },
  { left: '48%', width: '12%', height: '72%', delay: '-0.6s' },
  { left: '67%', width: '8%', height: '48%', delay: '-1.8s' },
  { left: '79%', width: '12%', height: '62%', delay: '-2.8s' },
]

export function HeroVisual({ awake, asset }) {
  const visualRef = useRef(null)

  const handlePointerMove = (event) => {
    if (event.pointerType === 'touch' || !visualRef.current) return
    const bounds = visualRef.current.getBoundingClientRect()
    const x = (event.clientX - bounds.left) / bounds.width - 0.5
    const y = (event.clientY - bounds.top) / bounds.height - 0.5
    visualRef.current.style.setProperty('--pointer-x', `${x.toFixed(3)}`)
    visualRef.current.style.setProperty('--pointer-y', `${y.toFixed(3)}`)
  }

  const handlePointerLeave = () => {
    visualRef.current?.style.setProperty('--pointer-x', '0')
    visualRef.current?.style.setProperty('--pointer-y', '0')
  }

  return (
    <div
      ref={visualRef}
      className={`landing-visual${awake ? ' is-awake' : ''}`}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
      aria-hidden="true"
    >
      {asset ? (
        asset.match(/\.(mp4|webm)(\?.*)?$/i) ? (
          <video className="landing-visual-asset" src={asset} autoPlay muted loop playsInline preload="none" />
        ) : (
          <img className="landing-visual-asset" src={asset} alt="" loading="lazy" />
        )
      ) : (
        <>
          <div className="landing-visual-grid" />
          <div className="landing-visual-halo" />
          <div className="landing-plant">
            <div className="landing-plant-ground" />
            <div className="landing-plant-structures">
              {structures.map((structure, index) => (
                <div
                  className={`landing-plant-column landing-plant-column-${index + 1}`}
                  key={structure.left}
                  style={{
                    left: structure.left,
                    width: structure.width,
                    height: structure.height,
                    '--column-delay': structure.delay,
                  }}
                >
                  <i />
                  <b />
                  <span />
                </div>
              ))}
              <div className="landing-pipe landing-pipe-upper" />
              <div className="landing-pipe landing-pipe-middle" />
              <div className="landing-pipe landing-pipe-lower" />
              <div className="landing-signal landing-signal-one" />
              <div className="landing-signal landing-signal-two" />
              <div className="landing-signal landing-signal-three" />
              <div className="landing-sensor landing-sensor-one" />
              <div className="landing-sensor landing-sensor-two" />
              <div className="landing-sensor landing-sensor-three" />
            </div>
          </div>
          <div className="landing-visual-caption">
            <span>MRPL · PROCESS SYSTEMS</span>
            <span>LOCAL VIEW / 01</span>
          </div>
        </>
      )}
    </div>
  )
}