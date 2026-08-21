import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, type Entity, type Project, type Shot } from './lib/api'
import Storyboard from './pages/Storyboard'
import Cast from './pages/Cast'
import Frames from './pages/Frames'
import Lobby from './pages/Lobby'
import Overview from './pages/Overview'
import Script from './pages/Script'
import Gallery from './pages/Gallery'
import ModelSetupGate from './ModelSetupGate'
import TaskActivity from './TaskActivity'

const STAGES = [
  { key: 'script', label: '剧本', to: '/script' },
  { key: 'cast', label: '设定', to: '/cast' },
  { key: 'board', label: '分镜', to: '/board' },
  { key: 'frames', label: '画面', to: '/frames' },
  { key: 'gallery', label: '总览', to: '/gallery' },
]
const STAGE_PATHS = ['/script', '/cast', '/board', '/frames', '/gallery', '/settings']

function Icon({ name }: { name: string }) {
  const p: Record<string, JSX.Element> = {
    home: <g><path d="M3 11l9-7 9 7" /><path d="M5 10v10h14V10" /></g>,
    overview: <g><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></g>,
    script: <path d="M5 3h9l5 5v13H5zM14 3v5h5" />,
    cast: <g><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></g>,
    board: <g><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 4v16" /></g>,
    frames: <g><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 9h4v10M17 5v14h4M7 5v4" /></g>,
    gallery: <g><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M3 16l5-4 4 3 4-5 5 6" /></g>,
    settings: <g><circle cx="12" cy="12" r="3" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3" /></g>,
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">{p[name]}</svg>
}

function Placeholder({ title }: { title: string }) {
  return <div className="center">{title} · 界面建设中</div>
}

const ETYPE_ZH: Record<string, string> = { character: '角色', scene: '场景', prop: '道具', costume: '服装' }

export default function App() {
  const [project, setProject] = useState<Project | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('duanju.theme') as 'dark' | 'light') || 'dark')
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('duanju.theme', theme)
  }, [theme])
  const [ready, setReady] = useState<{ done: number; total: number } | null>(null) // 画面就绪进度
  const [searchOpen, setSearchOpen] = useState(false)
  const [q, setQ] = useState('')
  const [sIdx, setSIdx] = useState<{ shots: Shot[]; ents: (Entity & { etype: string })[] } | null>(null)
  const navigate = useNavigate()
  const loc = useLocation()
  const inStage = STAGE_PATHS.some((p) => loc.pathname.startsWith(p)) // 阶段页才显示左轨；作品库/项目页独立
  const onLobby = loc.pathname === '/' || loc.pathname.startsWith('/projects') // 首页：不显示任何项目上下文

  // 启动：载入项目列表，恢复上次选中的项目
  useEffect(() => {
    let stopped = false
    let timer: number | null = null
    const load = () => {
      api.projects().then((ps) => {
        if (stopped) return
        const urlPid = new URLSearchParams(window.location.search).get('pid')
        const wantId = urlPid || localStorage.getItem('duanju.pid')
        const found = ps.find((p) => p.id === wantId) ?? null
        setProject(found)
        if (found) localStorage.setItem('duanju.pid', found.id)
      }).catch(() => {
        if (!stopped) timer = window.setTimeout(load, 2000)
      })
    }
    load()
    return () => {
      stopped = true
      if (timer != null) window.clearTimeout(timer)
    }
  }, [])

  const openProject = (p: Project) => {
    setProject(p)
    setSIdx(null)
    localStorage.setItem('duanju.pid', p.id)
    navigate('/overview')
  }

  // 真实进度：已出关键帧的镜头 ÷ 总镜头（后端 status 的"就绪"另有语义、从不翻转，不可用）
  useEffect(() => {
    if (!project) { setReady(null); return }
    let stale = false
    ;(async () => {
      try {
        const cs = await api.chapters(project.id)
        const [perCh, idx] = await Promise.all([
          Promise.all(cs.map((c) => api.shots(c.id).catch(() => [] as Shot[]))),
          api.frameIndex().catch(() => ({} as Record<string, Partial<Record<'first' | 'key' | 'last', string>>>)),
        ])
        const all = perCh.flat()
        const done = all.filter((s) => {
          const t = idx[s.id]
          return t && (t.key || t.first || t.last)
        }).length
        if (!stale) setReady({ done, total: all.length })
      } catch {}
    })()
    return () => { stale = true }
  }, [project?.id, loc.pathname])

  // ⌘K / Ctrl+K 打开搜索，Esc 关闭
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearchOpen(true) }
      if (e.key === 'Escape') setSearchOpen(false)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  // 首次打开搜索时建索引（镜头 + 实体）
  useEffect(() => {
    if (!searchOpen || !project || sIdx) return
    ;(async () => {
      try {
        const cs = await api.chapters(project.id)
        const perCh = await Promise.all(cs.map((c) => api.shots(c.id).catch(() => [] as Shot[])))
        const ents = (await Promise.all(Object.keys(ETYPE_ZH).map(async (t) =>
          (await api.entities(t, project.id).catch(() => [] as Entity[])).map((e) => ({ ...e, etype: t })),
        ))).flat()
        setSIdx({ shots: perCh.flat(), ents })
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchOpen, project?.id])

  const ql = q.trim().toLowerCase()
  const hitShots = ql && sIdx ? sIdx.shots.filter((s) =>
    (s.title || '').toLowerCase().includes(ql) || (s.script_excerpt || '').toLowerCase().includes(ql)).slice(0, 8) : []
  const hitEnts = ql && sIdx ? sIdx.ents.filter((e) => e.name.toLowerCase().includes(ql)).slice(0, 6) : []
  const goHit = (to: string) => { setSearchOpen(false); setQ(''); navigate(to) }

  return (
    <div className="app">
      <ModelSetupGate />
      <TaskActivity />
      <div className="topbar">
        <div className="brand" style={{ cursor: 'pointer' }} onClick={() => navigate('/projects')} title="返回作品库">
          <span className="dot" />
          <span>shotcat</span>
          <span className="brand-sub">短剧工作台</span>
        </div>
        {!onLobby && (
          <span className="crumb">
            {project ? <>项目 · <b>{project.name}</b></> : <>请选择或新建项目</>}
          </span>
        )}
        {!onLobby && project && ready && ready.total > 0 && (
          <div className="progress" title={`已出画面 ${ready.done} / ${ready.total} 镜`}>
            <div className="track"><div className="fill" style={{ width: `${Math.round((ready.done / ready.total) * 100)}%` }} /></div>
            <span className="pct">{Math.round((ready.done / ready.total) * 100)}%</span>
          </div>
        )}
        <div className="spacer" />
        {!onLobby && (
          <div className="search" style={{ cursor: 'pointer' }} onClick={() => project && setSearchOpen(true)}
            title={project ? '搜索镜头、角色、资产' : '先选择项目'}>
            <span>搜索镜头、角色、资产…</span><kbd>Ctrl K</kbd>
          </div>
        )}
        <div className="tb-icon" title={theme === 'dark' ? '切换浅色模式' : '切换黑金模式'} style={{ cursor: 'pointer' }}
          onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>{theme === 'dark' ? '☀' : '☾'}</div>
        {!onLobby && <div className="tb-icon" title="切换项目" onClick={() => navigate('/projects')} style={{ cursor: 'pointer' }}>⇄</div>}
        <div className="avatar">猫</div>
      </div>

      <div className="body" style={{ gridTemplateColumns: inStage ? '76px 1fr' : '1fr' }}>
        {inStage && (
          <div className="rail">
            <NavLink to="/overview" className="nav" title="返回项目概览">
              <Icon name="overview" />项目
            </NavLink>
            <div className="flow-line" />
            {STAGES.map((s, i) => (
              <div key={s.key} style={{ display: 'contents' }}>
                {i > 0 && <div className="flow-line" />}
                <NavLink to={s.to} className={({ isActive }) => 'nav' + (isActive ? ' active' : '')}>
                  <Icon name={s.key} />{s.label}
                </NavLink>
              </div>
            ))}
            <NavLink to="/settings" className="nav bottom"><Icon name="settings" />设置</NavLink>
          </div>
        )}

        <Routes>
          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<Lobby onOpen={openProject} />} />
          <Route path="/overview" element={<Overview project={project} onRatioChange={(r) => {
            const prev = project?.default_video_ratio || '9:16'
            setProject((p) => (p ? { ...p, default_video_ratio: r } : p))
            if (project) api.updateProject(project.id, { default_video_ratio: r }).catch(() => {
              setProject((p) => (p ? { ...p, default_video_ratio: prev } : p))
              alert('画幅保存失败，已恢复原值')
            })
          }} />} />
          <Route path="/board" element={<Storyboard project={project} />} />
          <Route path="/script" element={<Script project={project} />} />
          <Route path="/cast" element={<Cast project={project} />} />
          <Route path="/frames" element={<Frames project={project} />} />
          <Route path="/gallery" element={<Gallery project={project} />} />
          <Route path="/settings" element={<Placeholder title="设置" />} />
        </Routes>
      </div>

      {searchOpen && (
        <div className="modal-mask" onClick={() => setSearchOpen(false)}>
          <div className="smodal" onClick={(e) => e.stopPropagation()}>
            <input autoFocus className="s-in" value={q} placeholder="搜索镜头、角色、场景、道具、服装…"
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                if (hitShots[0]) goHit(`/frames?shot=${hitShots[0].id}`)
                else if (hitEnts[0]) goHit('/cast')
              }} />
            {!ql ? (
              <div className="s-tip">输入关键字 · 回车跳转第一个结果 · Esc 关闭</div>
            ) : hitShots.length === 0 && hitEnts.length === 0 ? (
              <div className="s-tip">{sIdx ? '没有匹配结果' : '索引加载中…'}</div>
            ) : (
              <div className="s-list">
                {hitShots.map((s) => (
                  <div className="s-item" key={s.id} onClick={() => goHit(`/frames?shot=${s.id}`)}>
                    <span className="k">镜头</span>
                    <span className="n">{String(s.index).padStart(2, '0')} · {s.title || s.script_excerpt?.slice(0, 24)}</span>
                    <span className="d">{(s.script_excerpt || '').slice(0, 40)}</span>
                  </div>
                ))}
                {hitEnts.map((e) => (
                  <div className="s-item" key={e.etype + e.id} onClick={() => goHit('/cast')}>
                    <span className="k">{ETYPE_ZH[e.etype]}</span>
                    <span className="n">{e.name}</span>
                    <span className="d">{(e.description || '').slice(0, 40)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
