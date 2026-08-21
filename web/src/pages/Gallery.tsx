import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fileUrl, CAMERA_ZH, type Chapter, type FrameType, type Project, type Shot } from '../lib/api'
import Lightbox from '../Lightbox'

const FT_LABEL: Record<FrameType, string> = { first: '首', key: '关', last: '尾' }

export default function Gallery({ project }: { project: Project | null }) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [shotsByCh, setShotsByCh] = useState<Record<string, Shot[]>>({})
  const [thumbs, setThumbs] = useState<Record<string, Partial<Record<FrameType, string>>>>({})
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [lb, setLb] = useState<string | null>(null)
  const [size, setSize] = useState<'s' | 'm' | 'l'>(() => (localStorage.getItem('duanju.galsize') as 's' | 'm' | 'l') || 'm')
  const navigate = useNavigate()
  const SIZE_MIN = { s: 180, m: 260, l: 380 }
  const pickSize = (k: 's' | 'm' | 'l') => { setSize(k); localStorage.setItem('duanju.galsize', k) }

  useEffect(() => {
    if (!project) return
    ;(async () => {
      try {
        const cs = await api.chapters(project.id)
        const [perCh, details, idx] = await Promise.all([
          Promise.all(cs.map((c) => api.shots(c.id).catch(() => [] as Shot[]))),
          api.shotDetails().catch(() => ({} as Record<string, any>)),
          api.frameIndex().catch(() => ({})),
        ])
        setChapters(cs)
        const m: Record<string, Shot[]> = {}
        cs.forEach((c, i) => {
          m[c.id] = perCh[i].map((x) => {
            const d = (details as Record<string, any>)[x.id]
            return d ? { ...x, camera_shot: d.camera_shot, duration: d.duration } : x
          })
        })
        setShotsByCh(m)
        setThumbs(idx)
        setOpen((o) => {
          const n = { ...o }
          cs.forEach((c) => { if (n[c.id] === undefined) n[c.id] = true })
          return n
        })
      } catch { /* 空态兜底 */ }
    })()
  }, [project?.id])

  if (!project) return <div className="center">请从作品库选择项目</div>

  const ratio = (project.default_video_ratio || '9:16').replace(':', ' / ')

  return (
    <div className="work">
      <div className="work-head">
        <h1>画面总览</h1>
        <div className="spacer" />
        <div className="seg">
          {(['s', 'm', 'l'] as const).map((k) => (
            <button key={k} className={'seg-btn' + (size === k ? ' on' : '')} onClick={() => pickSize(k)}>
              {{ s: '小', m: '中', l: '大' }[k]}
            </button>
          ))}
        </div>
      </div>

      {chapters.length === 0 ? (
        <div className="center" style={{ height: 180 }}>尚无剧本 · 先去「剧本」页粘贴正文</div>
      ) : (
        chapters.map((c) => {
          const list = shotsByCh[c.id] || []
          const done = list.filter((s) => thumbs[s.id]?.key || thumbs[s.id]?.first || thumbs[s.id]?.last).length
          return (
            <div className="ep-block" key={c.id}>
              <div className="ep-h fold" onClick={() => setOpen((o) => ({ ...o, [c.id]: !o[c.id] }))}>
                <span className="ep-caret">{open[c.id] ? '▾' : '▸'}</span>
                <span className="ep-t">第 {c.index} 集{c.title ? ` · ${c.title}` : ''}</span>
                <span className="ep-cnt">{list.length} 镜 · 已出图 {done}</span>
              </div>
              {open[c.id] && (
                <div className="gal-grid" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${SIZE_MIN[size]}px, 1fr))` }}>
                  {list.map((s) => {
                    const t = thumbs[s.id] || {}
                    const main = t.key || t.first || t.last
                    const fts = (['first', 'key', 'last'] as FrameType[]).filter((ft) => t[ft])
                    return (
                      <div className="gal-card" key={s.id} title={s.title || `镜头 ${s.index}`}>
                        {main ? (
                          <img src={fileUrl(main)} alt="" loading="lazy" style={{ aspectRatio: ratio }}
                            onClick={() => setLb(fileUrl(main))} />
                        ) : (
                          <div className="gal-ph" style={{ aspectRatio: ratio }}
                            onClick={() => navigate(`/frames?shot=${s.id}`)}>未生成</div>
                        )}
                        <div className="gal-cap" onClick={() => navigate(`/frames?shot=${s.id}`)} title="进入画面工作台">
                          <span className="no">{String(s.index).padStart(2, '0')}</span>
                          {s.camera_shot && <span className="cam">{CAMERA_ZH[s.camera_shot] || s.camera_shot}</span>}
                          {s.duration ? <span className="dur">{s.duration}s</span> : null}
                          <span className="spacer" />
                          <span className="fts">{fts.length ? fts.map((f) => FT_LABEL[f]).join('·') : '—'}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })
      )}

      <Lightbox url={lb} onClose={() => setLb(null)} />
    </div>
  )
}
