import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Project, type WorkflowInvalidation, type WorkflowRevision } from '../lib/api'

type Stats = { chapters: number; character: number; scene: number; prop: number; costume: number; actor: number; shots: number }

const STAGES: { to: string; label: string; desc: string; icon: string; main?: boolean }[] = [
  { to: '/script', label: '剧本', desc: '接原点产出 · 分集正文', icon: 'script' },
  { to: '/brain', label: '大脑', desc: '确认项目事实 · 锁定创作规则', icon: 'brain' },
  { to: '/cast', label: '设定', desc: '角色/场景/道具/服装 + 造型图', icon: 'cast' },
  { to: '/board', label: '分镜', desc: '镜头级时序 · 景别机位', icon: 'board', main: true },
  { to: '/frames', label: '画面', desc: '关键帧 · 生图', icon: 'frames' },
  { to: '/gallery', label: '总览', desc: '全集画面一览', icon: 'gallery' },
]

function SIcon({ n }: { n: string }) {
  const p: Record<string, JSX.Element> = {
    script: <path d="M5 3h9l5 5v13H5zM14 3v5h5" />,
    brain: <g><path d="M9 4a3 3 0 0 0-5 2.2A3.5 3.5 0 0 0 5 12a3.5 3.5 0 0 0 4 5.7V20" /><path d="M15 4a3 3 0 0 1 5 2.2A3.5 3.5 0 0 1 19 12a3.5 3.5 0 0 1-4 5.7V20M9 4v16M15 4v16M9 8h6M9 14h6" /></g>,
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
  const [invalidations, setInvalidations] = useState<WorkflowInvalidation[]>([])
  const [revisions, setRevisions] = useState<WorkflowRevision[]>([])
  const [restoringId, setRestoringId] = useState<string | null>(null)
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
      api.workflowInvalidations(pid).catch(() => []),
      api.workflowRevisions(pid).catch(() => []),
    ]).then(async ([chs, ch, sc, pr, co, ac, stale, history]) => {
      let shots = 0
      for (const c of chs) shots += (await api.shots(c.id).catch(() => [])).length
      setSt({ chapters: chs.length, character: ch.length, scene: sc.length, prop: pr.length, costume: co.length, actor: ac.length, shots })
      setInvalidations(stale)
      setRevisions(history)
    }).catch(() => setErr(true))
  }, [project?.id])

  if (!project) return <div className="center">请从作品库选择项目</div>

  const tiles = st ? [
    { k: '集数', v: st.chapters }, { k: '角色', v: st.character }, { k: '场景', v: st.scene },
    { k: '道具', v: st.prop }, { k: '服装', v: st.costume }, { k: '镜头', v: st.shots },
  ] : []

  const downloadRevision = async (revision: WorkflowRevision) => {
    const payload = await api.workflowRevisionSnapshot(project.id, revision.id)
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${project.name}-${revision.source_step}-v${revision.revision}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const restoreRevision = async (revision: WorkflowRevision) => {
    const accepted = window.confirm(
      `恢复到“${revision.reason || `${revision.source_step} v${revision.revision}`}”？\n\n`
      + '项目、剧本、设定、分镜和画面记录将回到该快照。系统会先自动保存当前状态，恢复后仍可撤回。',
    )
    if (!accepted) return
    setRestoringId(revision.id)
    try {
      const result = await api.restoreWorkflowRevision(project.id, revision.id)
      window.alert(`恢复完成。恢复前状态已保存为安全版本 ${result.safety_revision_id.slice(-8)}。`)
      window.location.reload()
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '恢复失败，请稍后重试')
      setRestoringId(null)
    }
  }

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

      {invalidations.length > 0 && (
        <section className="ov-impact" aria-label="需要重新确认的步骤">
          <div className="ov-impact-head">
            <div><strong>上游内容已变化</strong><span>旧结果仍然保留，但需要按顺序重新确认。</span></div>
            <b>{invalidations.length}</b>
          </div>
          {invalidations.map((item) => {
            const route = item.downstream_step === 'brain' ? '/brain'
              : item.downstream_step === 'cast' ? '/cast'
              : item.downstream_step === 'storyboard' ? '/board'
              : item.downstream_step === 'frames' ? '/frames' : '/gallery'
            return <button key={item.id} type="button" className="ov-impact-row" onClick={() => navigate(route)}>
              <span>{item.reason}</span><em>{item.affected_count} 项</em><i>前往处理 →</i>
            </button>
          })}
        </section>
      )}

      {revisions.length > 0 && (
        <section className="ov-history" aria-label="项目版本记录">
          <div className="ov-history-head"><strong>版本记录</strong><span>系统在重做前自动保存，可导出或恢复完整数据快照。</span></div>
          <div className="ov-history-list">
            {revisions.slice(0, 6).map((revision) => (
              <div key={revision.id} className="ov-history-row">
                <span>{revision.reason || `${revision.source_step} 重做前保存`}</span>
                <em>{revision.source_step} · v{revision.revision}</em>
                <div className="ov-history-actions">
                  <button type="button" onClick={() => void downloadRevision(revision)}>导出</button>
                  <button type="button" className="restore" disabled={restoringId !== null} onClick={() => void restoreRevision(revision)}>
                    {restoringId === revision.id ? '恢复中…' : revision.restored ? '再次恢复' : '恢复'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

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
