import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Project } from '../lib/api'

type Stats = { chapters: number; character: number; scene: number; prop: number; costume: number; actor: number; shots: number }

const STAGES: { to: string; label: string; desc: string; icon: string; main?: boolean }[] = [
  { to: '/script', label: '剧本', desc: '接原点产出 · 分集正文', icon: 'script' },
  { to: '/cast', label: '设定', desc: '角色/场景/道具/服装 + 造型图', icon: 'cast' },
  { to: '/board', label: '分镜', desc: '镜头级时序 · 景别机位', icon: 'board', main: true },
  { to: '/frames', label: '画面', desc: '关键帧 · 生图', icon: 'frames' },
  { to: '/gallery', label: '总览', desc: '全集画面一览', icon: 'gallery' },
]

function SIcon({ n }: { n: string }) {
  const p: Record<string, JSX.Element> = {
    script: <path d="M5 3h9l5 5v13H5zM14 3v5h5" />,
    cast: <g><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></g>,
    board: <g><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 4v16" /></g>,
    frames: <g><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 9h4v10M17 5v14h4M7 5v4" /></g>,
    gallery: <g><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M3 16l5-4 4 3 4-5 5 6" /></g>,
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">{p[n]}</svg>
}

export default function Overview({ project, onRatioChange }: { project: Project | null; onRatioChange?: (r: string) => void }) {
  const [st, setSt] = useState<Stats | null>(null)
  const [err, setErr] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!project) return
    const pid = project.id
    setSt(null); setErr(false)
    Promise.all([
      api.chapters(pid),
      api.entities('character', pid).catch(() => []),
      api.entities('scene', pid).catch(() => []),
      api.entities('prop', pid).catch(() => []),
      api.entities('costume', pid).catch(() => []),
      api.entities('actor', pid).catch(() => []),
    ]).then(async ([chs, ch, sc, pr, co, ac]) => {
      let shots = 0
      for (const c of chs) shots += (await api.shots(c.id).catch(() => [])).length
      setSt({ chapters: chs.length, character: ch.length, scene: sc.length, prop: pr.length, costume: co.length, actor: ac.length, shots })
    }).catch(() => setErr(true))
  }, [project?.id])

  if (!project) return <div className="center">请从作品库选择项目</div>

  const tiles = st ? [
    { k: '集数', v: st.chapters }, { k: '角色', v: st.character }, { k: '场景', v: st.scene },
    { k: '道具', v: st.prop }, { k: '服装', v: st.costume }, { k: '镜头', v: st.shots },
  ] : []

  return (
    <div className="work">
      <div className="ov-back" onClick={() => navigate('/projects')}>← 作品库</div>
      <div className="ov-hero">
        <div className="ov-title">{project.name}</div>
        <div className="ov-sub">{project.description || '短剧项目'}</div>
        <div className="ov-meta">
          <span>{project.style || '—'}</span><span>·</span>
          <label className="ratio-sel" title="画幅比例（项目级，影响生图/生视频）">
            画幅
            <select value={project.default_video_ratio || '9:16'} onChange={(e) => onRatioChange?.(e.target.value)}>
              {['9:16', '16:9', '1:1', '4:3', '3:4', '2:3', '3:2', '21:9'].map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
          <span>·</span>
          <span className="mono">{project.id}</span>
        </div>
      </div>

      <div className="ov-tiles">
        {tiles.map((t) => (
          <div className="ov-tile" key={t.k}>
            <div className="tv">{t.v}</div>
            <div className="tk">{t.k}</div>
          </div>
        ))}
        {!st && <div className="muted">{err ? '统计加载失败' : '统计加载中…'}</div>}
      </div>

      <div className="ov-stages-h">进入创作阶段</div>
      <div className="ov-stages">
        {STAGES.map((s) => (
          <div className={s.main ? 'ov-stage main' : 'ov-stage'} key={s.to} onClick={() => navigate(s.to)}>
            <div className="os-icon"><SIcon n={s.icon} /></div>
            <div className="os-label">{s.label}</div>
            <div className="os-desc">{s.desc}</div>
            {s.main && <span className="os-go">继续</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
