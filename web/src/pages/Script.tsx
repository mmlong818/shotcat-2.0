import { useEffect, useRef, useState, type TextareaHTMLAttributes } from 'react'
import { api, type Chapter, type Project } from '../lib/api'
import { usePipelineJobActive } from '../TaskActivity'
import { confirmOverwrite } from '../lib/confirmOverwrite'

// 随内容自动撑高的剧本编辑区（整页滚动，不在小框里滚）。
// 优先用原生 field-sizing:content（高度精确贴合内容，无内部滚动，滚轮正常穿透）；
// 不支持的浏览器退回 JS 量高，+4px 余量避免残留隐形滚动区吃掉滚轮。
const nativeAutoSize = typeof CSS !== 'undefined' && CSS.supports?.('field-sizing', 'content')
function AutoArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    if (nativeAutoSize) return
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.max(280, el.scrollHeight + 4) + 'px'
  }, [props.value])
  return <textarea ref={ref} {...props} />
}

export default function Script({ project }: { project: Project | null }) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [newText, setNewText] = useState('')
  const [saving, setSaving] = useState('')
  const [pipe, setPipe] = useState('')
  const [msg, setMsg] = useState('')
  const pipelineActive = usePipelineJobActive(project?.id, 'extract-setup')

  const load = () => {
    if (!project) return
    api.chapters(project.id).then((cs) => {
      setChapters(cs)
      const d: Record<string, string> = {}
      cs.forEach((c) => (d[c.id] = c.raw_text || ''))
      setDraft(d)
      // 默认只展开第一集；已手动开合过的保持原状
      setOpen((o) => {
        const n = { ...o }
        cs.forEach((c, i) => { if (n[c.id] === undefined) n[c.id] = i === 0 })
        return n
      })
    }).catch(() => setMsg('剧本加载失败'))
  }
  useEffect(load, [project?.id])

  async function addChapter() {
    if (!project || !newText.trim()) return
    const idx = chapters.length + 1
    setSaving('new'); setMsg('')
    try {
      await api.createChapter(project.id, idx, `第${idx}集`, newText.trim())
      setNewText('')
      // 后端 commit-after-yield：创建后立刻回读可能查不到新章节，轮询到出现为止
      for (let i = 0; i < 10; i++) {
        const cs = await api.chapters(project.id)
        if (cs.some((c) => c.index === idx)) break
        await new Promise((r) => setTimeout(r, 700))
      }
      load()
    } catch (e: any) { setMsg(e?.message || '创建失败') } finally { setSaving('') }
  }
  async function save(c: Chapter) {
    setSaving(c.id); setMsg('')
    try { await api.updateChapter(c.id, draft[c.id] || ''); setMsg(`第${c.index}集已保存`) }
    catch (e: any) { setMsg(e?.message || '保存失败') } finally { setSaving('') }
  }
  async function extract() {
    if (!project || pipe || pipelineActive) return
    const existingSetup = await Promise.all(
      ['character', 'scene', 'prop', 'costume'].map((type) => api.entities(type, project.id).catch(() => [])),
    )
    if (existingSetup.some((items) => items.length > 0) && !confirmOverwrite({
      step: '从剧本抽取设定',
      replaces: ['设定页中同名角色、场景、道具和服装的描述', '下一步锁定视觉词典时使用的设定基础'],
      consequence: '已有造型图、分镜和画面不会自动同步，新设定确认后需要按顺序重做后续步骤。',
    })) return
    setPipe('x'); setMsg('抽取设定中…（读全剧本，约 1 分钟）')
    try {
      const j = await api.runPipeline('extract-setup', project.id)
      await api.pollPipeline(j)
      setMsg('✓ 已按年龄、身份、妆发与服装拆出角色状态 → 去「设定」页锁定并生成对应造型图，再「分镜」页「AI 拆镜头」')
    } catch (e: any) { setMsg(e?.message || '抽取失败（pipeline 服务未起？）') } finally { setPipe('') }
  }

  if (!project) return <div className="center">请从作品库选择项目</div>

  return (
    <div className="work">
      <div className="work-head">
        <h1>剧本</h1>
        <div className="spacer" />
        <button className="btn primary" disabled={!!pipe || pipelineActive || chapters.length === 0} onClick={extract}>
          {pipe || pipelineActive ? '抽取设定中…' : '从剧本抽取设定'}
        </button>
      </div>
      {msg && <div className="sc-msg">{msg}</div>}

      {chapters.map((c) => (
        <div className="ep-block" key={c.id}>
          <div className="ep-h fold" onClick={() => setOpen((o) => ({ ...o, [c.id]: !o[c.id] }))}>
            <span className="ep-caret">{open[c.id] ? '▾' : '▸'}</span>
            <span className="ep-t">第 {c.index} 集 · {c.title}</span>
            <span className="ep-cnt">{(draft[c.id] || '').length} 字</span>
            <button className="btn ghost" disabled={saving === c.id}
              onClick={(e) => { e.stopPropagation(); save(c) }}>
              {saving === c.id ? '保存中…' : '保存'}
            </button>
          </div>
          {open[c.id] && (
            <AutoArea className="sc-area" value={draft[c.id] ?? ''}
              onChange={(e) => setDraft((d) => ({ ...d, [c.id]: e.target.value }))}
              placeholder="粘贴/编辑该集剧本正文（场景、动作、对白）…" />
          )}
        </div>
      ))}

      <div className="ep-block">
        <div className="ep-h"><span className="ep-t">＋ 新增一集</span>
          <button className="btn primary" disabled={saving === 'new' || !newText.trim()} onClick={addChapter}>
            {saving === 'new' ? '创建中…' : `保存为第 ${chapters.length + 1} 集`}
          </button>
        </div>
        <AutoArea className="sc-area" value={newText} onChange={(e) => setNewText(e.target.value)}
          placeholder={chapters.length === 0 ? '把《回声》这样的剧本正文粘贴到这里，保存后点右上角「从剧本抽取设定」自动抽出角色/场景/道具…' : '粘贴下一集剧本正文…'} />
      </div>
    </div>
  )
}
