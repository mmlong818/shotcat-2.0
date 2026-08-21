import { useEffect, useState } from 'react'
import { api, fileUrl, type Project } from '../lib/api'

const STYLES = ['真人都市', '真人科幻', '真人古装', '动漫科幻', '动漫3D', '国漫', '水墨画']
const VISUALS = ['现实', '动漫']
const RATIOS = ['9:16', '16:9', '1:1', '4:3', '3:4', '2:3', '3:2', '21:9']

export default function Lobby({ onOpen }: { onOpen: (p: Project) => void }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', style: '真人都市', visual_style: '现实', default_video_ratio: '9:16', description: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [covers, setCovers] = useState<Record<string, string>>({}) // 项目封面：第一个有图镜头的关键帧

  const load = () => {
    setLoading(true)
    api.projects().then((ps) => {
      setProjects(ps)
      // 镜头 id 形如 {pid}_chNN__shot_NNN，帧图索引按前缀归组即可得各项目封面
      api.frameIndex().then((idx) => {
        const m: Record<string, string> = {}
        const shotIds = Object.keys(idx).sort()
        for (const p of ps) {
          for (const sid of shotIds) {
            if (!sid.startsWith(p.id + '_')) continue
            const f = idx[sid].key || idx[sid].first || idx[sid].last
            if (f) { m[p.id] = fileUrl(f); break }
          }
        }
        setCovers(m)
      }).catch(() => {})
    }).catch(() => setProjects([])).finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function submit() {
    if (!form.name.trim()) return setErr('请输入剧名')
    setBusy(true); setErr('')
    try {
      const name = form.name.trim()
      const id = await api.createProject({ ...form, name })
      setCreating(false)
      const created = { ...form, id, name, progress: 0 }
      setForm({ name: '', style: '真人都市', visual_style: '现实', default_video_ratio: '9:16', description: '' })
      // 后端 commit-after-yield：创建后立刻拉列表可能还查不到新项目（时序缝隙），
      // 直接用表单数据构造项目对象进入，不依赖回读
      onOpen(created)
    } catch (e: any) {
      setErr(e?.message || '创建失败')
    } finally {
      setBusy(false)
    }
  }

  async function remove(e: React.MouseEvent, p: Project) {
    e.stopPropagation()
    if (!confirm(`删除项目《${p.name}》？此操作不可撤销。`)) return
    try {
      await api.deleteProject(p.id)
      load()
    } catch (x: any) {
      alert(x?.message || '删除失败')
    }
  }

  return (
    <div className="work">
      <div className="work-head">
        <h1>作品库</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setCreating(true)}>＋ 新建剧本项目</button>
      </div>

      {loading ? (
        <div className="center" style={{ height: 240 }}>加载中…</div>
      ) : projects.length === 0 ? (
        <div className="center" style={{ height: 240 }}>还没有项目 · 点右上角「新建剧本项目」开始</div>
      ) : (
        <div className="plobby">
          {projects.map((p) => (
            <div className="pcard" key={p.id} onClick={() => onOpen(p)}>
              <div className="cover">
                {covers[p.id]
                  ? <img src={covers[p.id]} alt={p.name} loading="lazy" />
                  : <span className="init">{p.name?.slice(0, 1) || '剧'}</span>}
              </div>
              <div className="pmeta">
                <div className="pn">{p.name}</div>
                <div className="ps">
                  <span>{p.style || '短剧'}</span>
                  <span className="del" title="删除" onClick={(e) => remove(e, p)}>✕</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {creating && (
        <div className="modal-mask" onClick={() => !busy && setCreating(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-h">新建剧本项目</div>
            <label className="fld"><span>剧名</span>
              <input autoFocus value={form.name} placeholder="例：替身总裁的辞职信"
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="fld"><span>题材风格</span>
              <select value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })}>
                {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="fld"><span>画面表现</span>
              <select value={form.visual_style} onChange={(e) => setForm({ ...form, visual_style: e.target.value })}>
                {VISUALS.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label className="fld"><span>画幅比例</span>
              <select value={form.default_video_ratio} onChange={(e) => setForm({ ...form, default_video_ratio: e.target.value })}>
                {RATIOS.map((r) => <option key={r} value={r}>{r}{r === '9:16' ? '（竖屏·短剧）' : r === '16:9' ? '（横屏）' : ''}</option>)}
              </select>
            </label>
            <label className="fld"><span>一句话简介</span>
              <input value={form.description} placeholder="选填"
                onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            {err && <div className="fld-err">{err}</div>}
            <div className="modal-foot">
              <button className="btn ghost" disabled={busy} onClick={() => setCreating(false)}>取消</button>
              <button className="btn primary" disabled={busy} onClick={submit}>{busy ? '创建中…' : '创建'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
