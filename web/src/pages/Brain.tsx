import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type Project,
  type ProjectBrainCategory,
  type ProjectBrainEntry,
  type ProjectBrainOrigin,
  type ProjectBrainSummary,
} from '../lib/api'

const CATEGORY_META: Record<ProjectBrainCategory, { label: string; note: string }> = {
  fact: { label: '原文事实', note: '剧本中明确写出的时间、人物和事件' },
  character: { label: '角色规则', note: '身份、关系、行为和不可违背的角色条件' },
  environment: { label: '环境规则', note: '空间结构、时间、天气和环境变化' },
  prop: { label: '道具规则', note: '关键物件的外观、归属和剧情作用' },
  style: { label: '视觉风格', note: '摄影、色彩、光线和画面表现的统一标准' },
  narrative: { label: '叙事骨架', note: '核心冲突、节拍、信息揭示和情绪目标' },
  continuity: { label: '连续性', note: '跨镜头、跨场次必须持续成立的状态' },
}

const ORIGIN_LABEL: Record<ProjectBrainOrigin, string> = {
  source: '原文', user: '用户确认', ai: 'AI 推断',
}

const EMPTY_FORM = {
  category: 'fact' as ProjectBrainCategory,
  title: '',
  content: '',
  origin: 'user' as ProjectBrainOrigin,
  source_ref: '',
}

export default function Brain({ project }: { project: Project | null }) {
  const [entries, setEntries] = useState<ProjectBrainEntry[]>([])
  const [summary, setSummary] = useState<ProjectBrainSummary | null>(null)
  const [category, setCategory] = useState<ProjectBrainCategory | 'all'>('all')
  const [form, setForm] = useState(EMPTY_FORM)
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!project) return
    try {
      const [nextEntries, nextSummary] = await Promise.all([
        api.projectBrain(project.id), api.projectBrainSummary(project.id),
      ])
      setEntries(nextEntries)
      setSummary(nextSummary)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '项目大脑读取失败')
    }
  }, [project?.id])

  useEffect(() => { void load() }, [load])

  const visibleEntries = useMemo(
    () => category === 'all' ? entries : entries.filter((item) => item.category === category),
    [category, entries],
  )

  if (!project) return <div className="center">请先选择项目</div>

  const createEntry = async () => {
    if (!form.title.trim() || !form.content.trim()) return
    setBusy('create')
    try {
      await api.createProjectBrainEntry(project.id, {
        ...form,
        title: form.title.trim(),
        content: form.content.trim(),
        source_ref: form.source_ref.trim(),
        status: form.origin === 'ai' ? 'draft' : 'confirmed',
        evidence: [],
        locked: form.origin !== 'ai',
      })
      setForm(EMPTY_FORM)
      setCreating(false)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy('')
    }
  }

  const patchEntry = async (entry: ProjectBrainEntry, patch: Partial<ProjectBrainEntry>) => {
    setBusy(entry.id)
    try {
      const updated = await api.updateProjectBrainEntry(project.id, entry.id, {
        ...patch, expected_version: entry.version,
      })
      setEntries((items) => items.map((item) => item.id === updated.id ? updated : item))
      setError('')
      const nextSummary = await api.projectBrainSummary(project.id)
      setSummary(nextSummary)
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新失败')
      await load()
    } finally {
      setBusy('')
    }
  }

  const deleteEntry = async (entry: ProjectBrainEntry) => {
    if (entry.locked || !window.confirm(`删除“${entry.title}”？此操作不会删除剧本或资产。`)) return
    setBusy(entry.id)
    try {
      await api.deleteProjectBrainEntry(project.id, entry.id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="work brain-page">
      <div className="work-head brain-head">
        <div>
          <div className="brain-kicker">SHOTCAT 2.0 · PROJECT BRAIN</div>
          <h1>项目大脑</h1>
          <p>把原文事实、用户决定和 AI 推断分开保存，后续拆镜头与生图只引用已确认规则。</p>
        </div>
        <button className="btn primary" onClick={() => setCreating((value) => !value)}>
          {creating ? '收起' : '新增规则'}
        </button>
      </div>

      <div className="brain-stats" aria-label="项目大脑概况">
        <div><b>{summary?.total ?? 0}</b><span>全部条目</span></div>
        <div><b>{summary?.confirmed ?? 0}</b><span>已确认</span></div>
        <div><b>{summary?.locked ?? 0}</b><span>已锁定</span></div>
        <div className={(summary?.ai_drafts ?? 0) > 0 ? 'needs-review' : ''}><b>{summary?.ai_drafts ?? 0}</b><span>AI 待确认</span></div>
      </div>

      {creating && (
        <section className="brain-compose" aria-label="新增项目规则">
          <div className="brain-compose-row">
            <label>分类<select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as ProjectBrainCategory })}>
              {Object.entries(CATEGORY_META).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
            </select></label>
            <label>来源<select value={form.origin} onChange={(e) => setForm({ ...form, origin: e.target.value as ProjectBrainOrigin })}>
              <option value="user">用户决定</option><option value="source">原文事实</option><option value="ai">AI 推断</option>
            </select></label>
            <label className="brain-source">来源位置<input value={form.source_ref} placeholder="例如：第 2 章第 4 段" onChange={(e) => setForm({ ...form, source_ref: e.target.value })} /></label>
          </div>
          <input className="brain-title-input" value={form.title} placeholder="一句话标题，例如：周诚从未进入过地下室" onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <textarea value={form.content} placeholder="写清楚必须持续成立的事实或规则，以及它会影响哪些场次或镜头。" onChange={(e) => setForm({ ...form, content: e.target.value })} />
          <div className="brain-compose-actions">
            <span>{form.origin === 'ai' ? 'AI 推断保存后进入待确认，不会自动锁定。' : '原文和用户决定默认确认并锁定，自动流程不得覆盖。'}</span>
            <button className="btn primary" disabled={busy === 'create' || !form.title.trim() || !form.content.trim()} onClick={createEntry}>保存规则</button>
          </div>
        </section>
      )}

      {error && <div className="brain-error" role="alert">{error}</div>}

      <div className="brain-filter" role="tablist" aria-label="项目大脑分类">
        <button className={category === 'all' ? 'on' : ''} onClick={() => setCategory('all')}>全部 <span>{entries.length}</span></button>
        {Object.entries(CATEGORY_META).map(([key, value]) => (
          <button key={key} className={category === key ? 'on' : ''} onClick={() => setCategory(key as ProjectBrainCategory)}>
            {value.label} <span>{summary?.by_category[key as ProjectBrainCategory] ?? 0}</span>
          </button>
        ))}
      </div>

      {visibleEntries.length === 0 ? (
        <div className="brain-empty">
          <strong>这里还没有{category === 'all' ? '项目规则' : CATEGORY_META[category].label}</strong>
          <p>先记录原文中不能被后续生成改变的事实。AI 抽取将在下一阶段写入“待确认”区域。</p>
        </div>
      ) : (
        <div className="brain-grid">
          {visibleEntries.map((entry) => (
            <article className={`brain-card origin-${entry.origin} status-${entry.status}`} key={entry.id}>
              <header>
                <span className="brain-category">{CATEGORY_META[entry.category].label}</span>
                <span className={`brain-origin ${entry.origin}`}>{ORIGIN_LABEL[entry.origin]}</span>
                <button className="brain-lock" aria-label={entry.locked ? '解除锁定' : '锁定规则'} disabled={busy === entry.id}
                  onClick={() => patchEntry(entry, { locked: !entry.locked })}>{entry.locked ? '已锁定' : '未锁定'}</button>
              </header>
              <h2>{entry.title}</h2>
              <p>{entry.content}</p>
              {entry.source_ref && <div className="brain-ref">来源：{entry.source_ref}</div>}
              <footer>
                <span>v{entry.version}</span>
                {entry.status === 'draft' && <button onClick={() => patchEntry(entry, { status: 'confirmed', locked: true })}>确认并锁定</button>}
                {entry.status !== 'rejected' && entry.origin === 'ai' && <button onClick={() => patchEntry(entry, { status: 'rejected', locked: false })}>拒绝</button>}
                {!entry.locked && <button className="danger-link" onClick={() => deleteEntry(entry)}>删除</button>}
              </footer>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
