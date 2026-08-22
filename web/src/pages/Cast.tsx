import { useEffect, useMemo, useRef, useState } from 'react'
import { api, fileUrl, type AssetImageBatchStatus, type AssetReference, type Entity, type EntityUsageShot, type Project } from '../lib/api'
import Lightbox from '../Lightbox'
import { usePipelineJobActive } from '../TaskActivity'
import { confirmOverwrite } from '../lib/confirmOverwrite'

const CATS = [
  { key: 'character', label: '角色' },
  { key: 'scene', label: '场景' },
  { key: 'prop', label: '道具' },
]
const DATA_CATS = [...CATS, { key: 'costume', label: '服装' }]
type EntityImage = { id: number; file_id: string; view_angle: string; name?: string }

const PROMPT_TEMPLATE_VERSION = 'prompt-clean-v11'
const DEFAULT_REALISTIC_STYLE = '电影感写实，统一中性影调，自然光影，细节清晰，设定集质感。'
const NON_CLOTHING_RE = /(手拿|拿着|握着|捧着|背着|抱着|携带|旧笔记本|笔记本|书本|汽水|道具)/

function repairLegacyDescriptionLine(value: string) {
  let repaired = value
  // 旧项目中少量中文说明曾被 UTF-8 误按西文读取一至两次；只修复这种特征文本。
  if (!/[ÃÂâã]/.test(repaired)) return repaired
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const codes = Array.from(repaired).map((char) => char.charCodeAt(0))
    if (codes.some((code) => code > 255)) break
    const decoded = new TextDecoder('utf-8', { fatal: false }).decode(Uint8Array.from(codes))
    if (!decoded || decoded.includes('\ufffd')) break
    repaired = decoded
    if (/[\u4e00-\u9fff【】]/.test(repaired)) break
  }
  return repaired
}

function descriptionLines(description?: string) {
  return (description || '').split(/\n+/).map(repairLegacyDescriptionLine)
}

function cleanCharacterLook(value: string) {
  return value
    .split(/\n+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .filter((part) => !NON_CLOTHING_RE.test(part))
    .join('；')
}

function stateReferenceName(description?: string) {
  const line = descriptionLines(description).find((value) => value.startsWith('【状态关系】派生自：'))
  return line?.replace('【状态关系】派生自：', '').trim() || ''
}

function stateRelationLabel(description?: string) {
  const line = descriptionLines(description).find((value) => value.startsWith('【状态关系】'))
  if (!line) return ''
  return line.includes('基准') ? '基准造型' : '派生状态'
}

type StrongVisualReference = { content: string; characters: string[]; scenes: string[] }

function strongVisualReference(description?: string): StrongVisualReference | null {
  const line = descriptionLines(description).find((value) => value.startsWith('【强关联参考】'))
  if (!line) return null
  const read = (label: string) => new RegExp(`${label}：([^；]*)`).exec(line)?.[1]?.trim() || ''
  const names = (value: string) => value && value !== '无' ? value.split('、').map((name) => name.trim()).filter(Boolean) : []
  return { content: read('内容'), characters: names(read('角色')), scenes: names(read('场景')) }
}

function visibleDescription(description?: string) {
  return descriptionLines(description)
    .join('\n')
    .split('【表演基线】')[0]
    .split(/\n+/)
    .map((value) => value.trim())
    .filter((value) => value && !value.startsWith('【状态关系】') && !value.startsWith('【强关联参考】'))
    .join('\n')
}

export default function Cast({ project }: { project: Project | null }) {
  const [data, setData] = useState<Record<string, Entity[]>>({})
  const [usageByEntity, setUsageByEntity] = useState<Record<string, EntityUsageShot[]>>({})
  const [tab, setTab] = useState('character')
  const [fresh, setFresh] = useState<Record<string, string>>({}) // 刚生成的 file_id
  const [busy, setBusy] = useState<string>('') // 正在生成的实体 id
  const [stage, setStage] = useState('')
  const [err, setErr] = useState('')
  const [batch, setBatch] = useState<AssetImageBatchStatus | null>(null)
  const [pipe, setPipe] = useState('') // 视觉词典生成中
  const pipelineActive = usePipelineJobActive(project?.id, 'visual-dict')
  const [angles, setAngles] = useState<Record<string, EntityImage[]>>({}) // 实体全部角度图
  const [references, setReferences] = useState<AssetReference[]>([])
  const [referenceQuery, setReferenceQuery] = useState('')
  const [referenceBusy, setReferenceBusy] = useState('')
  const [lb, setLb] = useState<string | null>(null)
  const [promptEdits, setPromptEdits] = useState<Record<string, string>>({})
  const [promptResetTick, setPromptResetTick] = useState(0)
  const [exporting, setExporting] = useState(false)
  const cancelledRef = useRef(false) // 卸载后停止轮询/批量
  // 挂载时必须重置：React 18 StrictMode(dev) 会模拟卸载再挂载，ref 跨挂载保留，
  // 不重置的话所有轮询一进来就"已取消"（任务照发、前端秒放弃）
  useEffect(() => { cancelledRef.current = false; return () => { cancelledRef.current = true } }, [])

  const loadAll = () => {
    if (!project) return Promise.resolve()
    return Promise.all([
      Promise.all(DATA_CATS.map((c) => api.entities(c.key, project.id).catch(() => [] as Entity[]))),
      Promise.all(CATS.map((c) => api.entityUsageSummary(c.key, project.id).catch(() => []))),
      api.assetReferences(project.id).catch(() => [] as AssetReference[]),
    ]).then(([lists, usageLists, referenceRows]) => {
      const map: Record<string, Entity[]> = {}
      DATA_CATS.forEach((c, i) => (map[c.key] = lists[i]))
      setData(map)
      const usageMap: Record<string, EntityUsageShot[]> = {}
      usageLists.flat().forEach((summary) => { usageMap[summary.entity_id] = summary.shots })
      setUsageByEntity(usageMap)
      setReferences(referenceRows)
    })
  }
  useEffect(() => { void loadAll() }, [project])
  useEffect(() => {
    if (!project) return
    const versionKey = `shotcat:promptTemplateVersion:${project.id}`
    const editsKey = `shotcat:promptEdits:${project.id}`
    const savedVersion = localStorage.getItem(versionKey)
    if (savedVersion !== PROMPT_TEMPLATE_VERSION) {
      localStorage.removeItem(editsKey)
      localStorage.setItem(versionKey, PROMPT_TEMPLATE_VERSION)
      setPromptEdits({})
      return
    }
    const savedPrompts = localStorage.getItem(editsKey)
    setPromptEdits(savedPrompts ? JSON.parse(savedPrompts) : {})
  }, [project?.id])

  useEffect(() => {
    if (!project) return
    localStorage.setItem(`shotcat:promptEdits:${project.id}`, JSON.stringify(promptEdits))
  }, [project?.id, promptEdits])

  useEffect(() => {
    if (!project) return
    const batchId = localStorage.getItem(`shotcat:assetImageBatch:${project.id}`)
    if (!batchId || batch) return
    let stopped = false
    ;(async () => {
      try {
        const first = await api.assetImageBatchStatus(batchId)
        if (stopped) return
        if (first.status === 'succeeded' || first.status === 'failed' || first.status === 'cancelled') {
          localStorage.removeItem(`shotcat:assetImageBatch:${project.id}`)
          await loadAll()
          return
        }
        setBatch(first)
        const done = await api.pollAssetImageBatch(
          batchId,
          (s) => !stopped && setBatch(s),
          () => stopped || cancelledRef.current,
        )
        if (!stopped && done) {
          localStorage.removeItem(`shotcat:assetImageBatch:${project.id}`)
          setErr(done.status === 'cancelled' ? `已停止队列，保留已完成的 ${done.succeeded} 项。` : done.failed ? `批量生成完成，失败 ${done.failed} 项。` : '批量生成完成。')
          await loadAll()
          setBatch(null)
        }
      } catch {
        localStorage.removeItem(`shotcat:assetImageBatch:${project.id}`)
      }
    })()
    return () => { stopped = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id])

  const items = data[tab] ?? []
  const visibleReferences = references.filter((reference) => (
    reference.entity_type === tab
    && (!referenceQuery.trim() || reference.display_name.toLowerCase().includes(referenceQuery.trim().toLowerCase()))
  ))

  async function patchReference(reference: AssetReference, patch: Partial<Pick<AssetReference, 'display_name' | 'is_adopted' | 'is_locked'>>) {
    if (!project || referenceBusy) return
    setReferenceBusy(reference.id); setErr('')
    try {
      await api.updateAssetReference(project.id, reference.id, patch)
      setReferences(await api.assetReferences(project.id))
    } catch (error: any) {
      setErr(error?.message || '参考版本更新失败')
    } finally {
      setReferenceBusy('')
    }
  }

  const loadEntityImages = async (type: string, id: string) => {
    const imgs = await api.entityImages(type, id).catch(() => [])
    setAngles((m) => ({ ...m, [id]: imgs.filter((x: any) => x.file_id) }))
  }

  const setEntityNameLocal = (type: string, id: string, name: string) => {
    setData((m) => ({
      ...m,
      [type]: (m[type] ?? []).map((x) => x.id === id ? { ...x, name } : x),
    }))
  }

  // 当前 tab 实体的全部角度图（BACK/DETAIL 等多角度参考也要能看到）
  useEffect(() => {
    let stale = false
    ;(async () => {
      const m: Record<string, EntityImage[]> = {}
      for (const e of items) {
        const imgs = await api.entityImages(tab, e.id).catch(() => [])
        m[e.id] = imgs.filter((x: any) => x.file_id)
      }
      if (!stale) setAngles(m)
    })()
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, data])
  const roleLabel = useMemo(() => DATA_CATS.find((c) => c.key === tab)?.label ?? '', [tab])
  const thumbOf = (e: Entity) => (fresh[e.id] ? fileUrl(fresh[e.id]) : e.thumbnail || '')
  const visualDesc = (e: Entity | null) => visibleDescription(e?.description)
  const stateBase = (type: string, e: Entity) => {
    const name = stateReferenceName(e.description)
    return name ? (data[type] ?? []).find((candidate) => candidate.name === name) ?? null : null
  }
  const stateBaseFileId = (type: string, e: Entity) => {
    const base = stateBase(type, e)
    if (!base) return ''
    return fresh[base.id] || angles[base.id]?.[0]?.file_id || ''
  }
  const strongReferenceAssets = (type: string, e: Entity) => {
    if (type !== 'prop') return [] as { type: string; entity_id: string }[]
    const relation = strongVisualReference(e.description)
    if (!relation) return [] as { type: string; entity_id: string }[]
    const refs = [
      ...relation.characters.map((name) => ({ type: 'character', entity_id: (data.character || []).find((item) => item.name === name)?.id || '' })),
      ...relation.scenes.map((name) => ({ type: 'scene', entity_id: (data.scene || []).find((item) => item.name === name)?.id || '' })),
    ].filter((item) => item.entity_id)
    return Array.from(new Map(refs.map((item) => [`${item.type}:${item.entity_id}`, item])).values())
  }
  const strongReferenceFileIds = async (type: string, e: Entity) => {
    const refs = strongReferenceAssets(type, e)
    const fileIds: string[] = []
    for (const ref of refs) {
      let fileId = fresh[ref.entity_id] || angles[ref.entity_id]?.[0]?.file_id || ''
      if (!fileId) {
        const images = await api.entityImages(ref.type, ref.entity_id)
        fileId = images.find((image) => image.file_id)?.file_id || ''
      }
      if (!fileId) throw new Error('请先生成强关联的角色和场景参考图，再生成该道具。')
      fileIds.push(fileId)
    }
    return Array.from(new Set(fileIds))
  }

  const styleClause = () => {
    return project?.visual_style === '动漫'
      ? '【风格】统一动画/动漫渲染，一致的线条与上色、统一角色比例；'
      : `【风格】${DEFAULT_REALISTIC_STYLE}`
  }
  const DESIGN_PREFIX: Record<string, string> = {
    character: '角色设定三视图：正面、侧面、背面横向并排，纯净中性背景，清晰展示外貌、发型、身形比例和本造型状态的服装细节。',
    actor: '演员形象设定图，半身或全身，纯净中性背景，清晰展示五官与形象细节，设定集风格。主体：',
    scene: '空无一人的场景环境：',
    prop: '道具设计图，纯净中性背景，主体居中，完整清晰展示道具的整体形态、材质与特定细节(刻痕/锈迹/文字等)，产品/设定集视角。道具：',
  }
  const designPrompt = (type: string, e: Entity) => {
    let body = visualDesc(e)
    if (!body) return ''
    if (type === 'scene') {
      return [(DESIGN_PREFIX[type] || '') + body, styleClause()].filter(Boolean).join(' ')
    }
    if (type === 'character') {
      return [
        DESIGN_PREFIX[type],
        `角色造型：${cleanCharacterLook(body) || body}`,
        styleClause(),
      ].filter(Boolean).join(' ')
    }
    const relation = type === 'prop' ? strongVisualReference(e.description) : null
    const strongContent = relation?.content
      ? `道具内部画面内容：${relation.content}；其中的人物和地点必须严格匹配所附参考图。`
      : ''
    return [(DESIGN_PREFIX[type] || '') + body, strongContent, styleClause()].filter(Boolean).join(' ')
  }
  const promptKey = (type: string, id: string) => (
    `${type}:${PROMPT_TEMPLATE_VERSION}:${id}`
  )
  const promptFor = (type: string, e: Entity) => {
    const saved = promptEdits[promptKey(type, e.id)]
    return saved ?? designPrompt(type, e)
  }
  const setPromptFor = (type: string, e: Entity, value: string) => {
    setPromptEdits((m) => ({ ...m, [promptKey(type, e.id)]: value }))
  }
  const clearSavedPrompts = () => {
    if (!project) return
    Object.keys(localStorage)
      .filter((key) => key.startsWith('shotcat:promptEdits:'))
      .forEach((key) => localStorage.removeItem(key))
    localStorage.setItem(`shotcat:promptTemplateVersion:${project.id}`, PROMPT_TEMPLATE_VERSION)
    setPromptEdits({})
    setPromptResetTick((v) => v + 1)
    setErr('已清除旧提示词，并按最新干净模板重建。')
  }
  const ensureSceneGuard = (prompt: string) => (
    prompt
  )

  async function renameEntity(e: Entity, value: string) {
    const name = value.trim()
    if (!name) {
      await loadAll()
      return
    }
    setEntityNameLocal(tab, e.id, name)
    try {
      await api.updateEntity(tab, e.id, { name })
      await loadEntityImages(tab, e.id)
    } catch (x: any) {
      setErr(x?.message || '名称保存失败')
      await loadAll()
      await loadEntityImages(tab, e.id)
    }
  }

  async function deleteEntity(e: Entity) {
    if (busy || batch) return
    const dependents = (data[tab] ?? []).filter((item) => stateReferenceName(item.description) === e.name)
    if (dependents.length) {
      setErr(`「${e.name}」仍是 ${dependents.length} 个派生状态的基准，请先删除派生状态。`)
      return
    }
    const baseName = stateReferenceName(e.description)
    const base = stateBase(tab, e)
    if (baseName && !base) {
      setErr(`找不到派生状态「${e.name}」的基准造型「${baseName}」，为避免镜头失去参考，不能删除。`)
      return
    }
    const usage = usageByEntity[e.id] ?? []
    const typeLabel = tab === 'character' ? '角色及其造型图、镜头关联' : `${roleLabel}及其造型图`
    const fallbackNotice = base ? `已使用它的 ${usage.length} 个镜头会自动改用基准造型「${base.name}」。` : `这会同时删除${typeLabel}。`
    if (!window.confirm(`删除「${e.name}」？${fallbackNotice}`)) return
    setBusy(e.id); setErr('')
    try {
      const result = await api.deleteEntity(tab, e.id)
      setData((current) => ({ ...current, [tab]: (current[tab] ?? []).filter((item) => item.id !== e.id) }))
      setAngles((current) => {
        const next = { ...current }
        delete next[e.id]
        return next
      })
      setFresh((current) => {
        const next = { ...current }
        delete next[e.id]
        return next
      })
      setPromptEdits((current) => {
        const next = { ...current }
        delete next[promptKey(tab, e.id)]
        return next
      })
      await loadAll()
      setErr(result.fallback_entity_name
        ? `已删除「${e.name}」，${result.reassigned_shot_count} 个镜头已改用基准造型「${result.fallback_entity_name}」。`
        : `已删除「${e.name}」。可回到「剧本」页再次「从剧本抽取设定」重新建立资产。`)
    } catch (x: any) {
      setErr(x?.message || '删除失败')
      await loadAll()
    } finally {
      setBusy('')
    }
  }

  async function gen(e: Entity) {
    if (!project || busy) return
    const projectId = project.id
    if (thumbOf(e) && !confirmOverwrite({
      step: `重新生成「${e.name}」造型图`,
      replaces: ['当前造型图', '后续新生成镜头所使用的设定参考图'],
      consequence: '已经生成的镜头画面不会自动更新，如需一致请在画面页重新生成对应镜头。',
    })) return
    setBusy(e.id); setErr(''); setStage('生成中…')
    try {
      const prompt = (tab === 'scene' ? ensureSceneGuard(promptFor(tab, e)) : promptFor(tab, e)).trim()
      if (!prompt) throw new Error('提示词为空，请先填写后再生成')
      const base = stateBase(tab, e)
      let referenceFileId = stateBaseFileId(tab, e)
      if (base && !referenceFileId) {
        const baseImages = await api.entityImages(tab, base.id)
        referenceFileId = baseImages.find((image) => image.file_id)?.file_id || ''
      }
      if (base && !referenceFileId) throw new Error(`请先生成基准造型「${base.name}」；派生状态不能独立生成。`)
      const strongReferenceFiles = await strongReferenceFileIds(tab, e)
      const references = Array.from(new Set([referenceFileId, ...strongReferenceFiles].filter(Boolean)))
      const fid = await api.generateEntityImage(tab, e.id, prompt, references, (p) => setStage(`生成中… ${p}%`), () => cancelledRef.current)
      setFresh((m) => ({ ...m, [e.id]: fid }))
      await loadEntityImages(tab, e.id)
      setReferences(await api.assetReferences(projectId))
    } catch (x: any) {
      setErr(`${e.name}：${x?.message || '生成失败'}`)
    } finally {
      setBusy(''); setStage('')
    }
  }

  async function uploadDesign(e: Entity, file: File | undefined) {
    if (!project || !file || busy || batch) return
    if (thumbOf(e) && !confirmOverwrite({
      step: `上传「${e.name}」认可设计稿`,
      replaces: ['当前造型图', '后续新生成镜头所使用的设定参考图'],
      consequence: '已经生成的镜头画面不会自动更新，如需一致请在画面页重新生成对应镜头。',
    })) return
    setBusy(e.id); setErr(''); setStage('上传设计稿中…')
    try {
      const fileId = await api.uploadEntityDesign(tab, e.id, project.id, e.name, file)
      setFresh((current) => ({ ...current, [e.id]: fileId }))
      await loadEntityImages(tab, e.id)
      await loadAll()
      setErr(`已采用「${e.name}」的上传设计稿；后续镜头会按该名称和图片作为参考。`)
    } catch (error: any) {
      setErr(`${e.name}：${error?.message || '设计稿上传失败'}`)
    } finally {
      setBusy(''); setStage('')
    }
  }
  async function genMissing() {
    if (!project || batch) return
    setErr('')
    setStage('提交任务中…')
    try {
      const queue: { type: string; id: string; name: string; image_id: number; prompt: string; reference_type?: string; reference_entity_id?: string; reference_assets?: { type: string; entity_id: string }[] }[] = []
      for (const c of CATS) {
        for (const e of data[c.key] ?? []) {
          if (cancelledRef.current) break
          const prompt = promptFor(c.key, e).trim()
          if (!prompt || thumbOf(e)) continue
          const image_id = await api.ensureImageSlot(c.key, e.id)
          const base = stateBase(c.key, e)
          if (stateReferenceName(e.description) && !base) throw new Error(`找不到「${e.name}」的基准造型，无法提交派生状态。`)
          queue.push({
            type: c.key,
            id: e.id,
            name: e.name,
            image_id,
            prompt,
            ...(base ? { reference_type: c.key, reference_entity_id: base.id } : {}),
            ...(strongReferenceAssets(c.key, e).length ? { reference_assets: strongReferenceAssets(c.key, e) } : {}),
          })
        }
      }
      if (!queue.length) {
        setErr('没有可提交的缺失造型：需要未生成图片，且提示词不为空。')
        return
      }
      const orderedQueue: typeof queue = []
      const remaining = new Map(queue.map((item) => [`${item.type}:${item.id}`, item]))
      const appendWithBase = (item: (typeof queue)[number]) => {
        const key = `${item.type}:${item.id}`
        if (!remaining.has(key)) return
        const baseKey = item.reference_entity_id ? `${item.reference_type}:${item.reference_entity_id}` : ''
        if (baseKey) {
          const base = remaining.get(baseKey)
          if (base) appendWithBase(base)
        }
        for (const reference of item.reference_assets || []) {
          const related = remaining.get(`${reference.type}:${reference.entity_id}`)
          if (related) appendWithBase(related)
        }
        remaining.delete(key)
        orderedQueue.push(item)
      }
      queue.forEach(appendWithBase)
      const created = await api.createAssetImageBatch(orderedQueue)
      localStorage.setItem(`shotcat:assetImageBatch:${project.id}`, created.batch_id)
      setBatch({
        batch_id: created.batch_id,
        status: 'queued',
        total: created.total,
        queued: created.total,
        running: 0,
        succeeded: 0,
        failed: 0,
        cancelled: 0,
        items: [],
      })
      const done = await api.pollAssetImageBatch(
        created.batch_id,
        (s) => setBatch(s),
        () => cancelledRef.current,
      )
      if (done) {
        localStorage.removeItem(`shotcat:assetImageBatch:${project.id}`)
        setErr(done.status === 'cancelled' ? `已停止队列，保留已完成的 ${done.succeeded} 项。` : done.failed ? `批量生成完成，失败 ${done.failed} 项。` : '批量生成完成。')
        await loadAll()
      }
    } catch (x: any) {
      setErr(x?.message || '批量提交失败')
    } finally {
      setStage('')
      setBatch(null)
    }
  }
  async function stopMissingGeneration() {
    if (!batch || !project) return
    if (!window.confirm('停止当前批量生成？正在执行的图片任务也会收到取消请求，已经完成的图片会保留。')) return
    try {
      const stopped = await api.cancelAssetImageBatch(batch.batch_id)
      setBatch(stopped)
      setErr('已请求停止队列，正在执行的任务将尽快取消。')
    } catch (x: any) {
      setErr(x?.message || '停止队列失败')
    }
  }
  async function lockVisualDict() {
    if (!project || pipe || pipelineActive) return
    const completionKey = `shotcat:completed:visual-dict:${project.id}`
    const hasExistingOutput = localStorage.getItem(completionKey) === '1'
      || DATA_CATS.some((category) => (data[category.key] || []).some((entity) => Boolean(thumbOf(entity))))
    if (hasExistingOutput && !confirmOverwrite({
      step: '锁定角色状态与视觉词典',
      replaces: ['设定页的角色、场景和道具视觉描述', '下一步生成造型图所使用的提示词'],
      consequence: '已有造型图不会自动改变；要应用新的视觉词典，需要重新生成相应造型图。',
    })) return
    setPipe('dict'); setErr('')
    try {
      const job = await api.runPipeline('visual-dict', project.id)
      await api.pollPipeline(job, 200, () => cancelledRef.current)
      localStorage.setItem(completionKey, '1')
      loadAll()
    } catch (x: any) { setErr(x?.message || '视觉词典生成失败') } finally { setPipe('') }
  }

  async function exportAssets() {
    if (!project || exporting) return
    setExporting(true)
    setErr('')
    try {
      const response = await api.exportProjectAssets(project.id)
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.message || `导出失败 ${response.status}`)
      }
      const contentDisposition = response.headers.get('Content-Disposition') || ''
      const encodedName = /filename\*=UTF-8''([^;]+)/.exec(contentDisposition)?.[1]
      const filename = encodedName ? decodeURIComponent(encodedName) : `${project.name || '项目'}_设定图.zip`
      const blobUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (error: any) {
      setErr(error?.message || '导出设定图失败')
    } finally {
      setExporting(false)
    }
  }

  if (!project) return <div className="center">未找到项目 · 请先用 bridge 导入剧本</div>

  return (
    <div className="work">
      <div className="work-head">
        <h1>造型</h1>
        <div className="spacer" />
        <button className="btn ghost" disabled={exporting || !!batch || !!busy} onClick={exportAssets}>
          {exporting ? '打包导出中…' : '批量导出设定'}
        </button>
        <button className="btn ghost" disabled={!!pipe || pipelineActive || !!busy} onClick={lockVisualDict}>
          {pipe === 'dict' || pipelineActive ? '锁定中…（读全剧本）' : '① 锁定角色状态与视觉词典'}
        </button>
        <button className="btn primary" disabled={!!batch || !!busy || !!pipe || pipelineActive} onClick={genMissing}>
          {batch ? `排队生成 ${batch.succeeded + batch.failed + batch.cancelled}/${batch.total}` : stage === '提交任务中…' ? '提交任务中…' : '② 提交全部缺失造型任务'}
        </button>
        {batch && <button className="btn ghost" onClick={stopMissingGeneration}>停止排队</button>}
      </div>

      <div className="tabs">
        {DATA_CATS.map((c) => (
          <button key={c.key} className={'tab' + (c.key === tab ? ' on' : '')} onClick={() => { setTab(c.key); setErr('') }}>
            {c.label} <span className="cnt">{(data[c.key] ?? []).length}</span>
          </button>
        ))}
      </div>

      <section className="reference-rail" aria-label="参考资产轨">
        <div className="reference-rail-head">
          <div>
            <div className="tone-title">参考资产轨</div>
            <div className="tone-sub">每次上传或生成都保留版本；“已采用”会进入后续镜头，“已锁定”不会被新生成结果自动替换。</div>
          </div>
          <div className="reference-summary">
            <span>已采用 {visibleReferences.filter((x) => x.is_adopted).length}</span>
            <span>已锁定 {visibleReferences.filter((x) => x.is_locked).length}</span>
            <input value={referenceQuery} onChange={(event) => setReferenceQuery(event.target.value)} placeholder="搜索参考名称" aria-label="搜索参考资产" />
          </div>
        </div>
        <div className="reference-track">
          {visibleReferences.map((reference) => (
            <article className={`reference-card${reference.is_adopted ? ' adopted' : ''}`} key={reference.id}>
              <button className="reference-preview" onClick={() => setLb(fileUrl(reference.file_id))} aria-label={`查看${reference.display_name}`}>
                <img src={fileUrl(reference.file_id)} alt="" />
              </button>
              <div className="reference-meta">
                <input
                  defaultValue={reference.display_name}
                  aria-label="参考版本名称"
                  disabled={referenceBusy === reference.id}
                  onBlur={(event) => {
                    const name = event.target.value.trim()
                    if (name && name !== reference.display_name) void patchReference(reference, { display_name: name })
                  }}
                />
                <div className="reference-flags">
                  <span>V{reference.version}</span>
                  <span>{reference.source === 'upload' ? '用户上传' : 'AI 生成'}</span>
                  {reference.is_adopted && <strong>已采用</strong>}
                </div>
                <div className="reference-actions">
                  {!reference.is_adopted && <button className="btn ghost" onClick={() => void patchReference(reference, { is_adopted: true })}>采用</button>}
                  <button className="btn ghost" onClick={() => void patchReference(reference, { is_locked: !reference.is_locked })}>
                    {reference.is_locked ? '解除锁定' : '锁定'}
                  </button>
                </div>
              </div>
            </article>
          ))}
          {visibleReferences.length === 0 && <div className="reference-empty">首次上传或生成造型后，这里会保留可追溯版本。</div>}
        </div>
      </section>

      <div className="tone-panel">
        <div className="tone-head">
          <div>
            <div className="tone-title">提示词管理</div>
            <div className="tone-sub">这里显示的是每张设定图最终会送去生成的提示词；艺术指导已前置到剧本抽取和视觉词典阶段。</div>
          </div>
          <button className="btn ghost" onClick={clearSavedPrompts} disabled={!!busy || !!batch}>清除旧提示词</button>
        </div>
      </div>

      {err && <div className="fld-err" style={{ marginBottom: 12 }}>{err}</div>}

      <div className="cast-grid">
        {items.map((e) => {
          const url = thumbOf(e)
          const busyThis = busy === e.id
          const currentPrompt = promptFor(tab, e)
          const canGenerate = !!currentPrompt.trim()
          const relationLabel = stateRelationLabel(e.description)
          const isDerivedState = !!stateReferenceName(e.description)
          const strongRelation = tab === 'prop' ? strongVisualReference(e.description) : null
          const usage = usageByEntity[e.id] ?? []
          return (
            <div className="cast-card" key={e.id}>
              <div className="cc-img">
                {url ? (
                  <img className="zoomable" src={url} alt={e.name} title="点击放大" onClick={() => setLb(url)} />
                ) : busyThis ? (
                  <div className="cc-ph"><div className="plus">◔</div>{stage}</div>
                ) : (
                  <div className="cc-ph"><span>○ 未生成</span></div>
                )}
              </div>
              <div className="cc-body">
                <div className="cc-h">
                  <input
                    className="n cc-name-input"
                    value={e.name}
                    aria-label="设计名称"
                    title="点击修改设计名称，后续任务会使用这个名称"
                    disabled={!!busy || !!batch}
                    onChange={(ev) => setEntityNameLocal(tab, e.id, ev.target.value)}
                    onBlur={(ev) => renameEntity(e, ev.target.value)}
                  />
                  <span className="role">{relationLabel || roleLabel}</span>
                  <span className="id">{e.id.split('__').pop()}</span>
                </div>
                <div className="cc-desc">{visualDesc(e) || '（未锁定，先跑「① 锁定视觉词典」）'}</div>
                {strongRelation && (
                  <div className="cc-desc">强关联：{strongRelation.content || '道具内画面'}；角色 {strongRelation.characters.join('、') || '无'}；场景 {strongRelation.scenes.join('、') || '无'}</div>
                )}
                <div className="cc-desc">
                  {usage.length
                    ? `画面使用（${usage.length}）：${usage.map((shot) => `第${shot.shot_index}镜 ${shot.title}`).join('、')}`
                    : '当前未被镜头画面使用'}
                </div>
                <div className="cc-prompt">
                  <div className="prompt-label">{tab === 'character' ? '角色状态生成提示词' : '生成提示词'}{tab === 'scene' ? ` · ${PROMPT_TEMPLATE_VERSION}` : ''}</div>
                  <textarea
                    key={`${promptResetTick}:${tab}:${e.id}`}
                    className="prompt-edit"
                    value={currentPrompt}
                    disabled={busyThis || !!batch}
                    onChange={(ev) => setPromptFor(tab, e, ev.target.value)}
                    placeholder="未锁定设定时不会自动生成提示词；请先跑视觉词典，或手动填写。"
                  />
                  <div className="prompt-actions">
                    <button className="btn ghost" disabled={busyThis || !!batch} onClick={() => setPromptFor(tab, e, designPrompt(tab, e))}>
                      按当前基调重置
                    </button>
                    <button className="btn ghost" disabled={busyThis || !!batch} onClick={() => deleteEntity(e)}>
                      删除{isDerivedState ? '派生状态' : tab === 'character' ? '角色' : roleLabel}
                    </button>
                  </div>
                </div>
                <div className="cc-image-actions">
                  <label className={`btn ghost cc-upload${busy || batch ? ' disabled' : ''}`}>
                    上传认可设计稿
                    <input
                      type="file"
                      accept="image/*"
                      disabled={!!busy || !!batch}
                      onChange={(event) => {
                        const file = event.target.files?.[0]
                        event.target.value = ''
                        void uploadDesign(e, file)
                      }}
                    />
                  </label>
                  <button className="btn primary" disabled={!!busy || !!batch || !canGenerate} onClick={() => gen(e)}>
                    {busyThis ? (stage || '处理中…') : url ? '重新生成造型图' : '生成造型图'}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
        {items.length === 0 && <div className="muted" style={{ padding: 20 }}>该分类暂无资产</div>}
      </div>

      <Lightbox url={lb} onClose={() => setLb(null)} />
    </div>
  )
}
