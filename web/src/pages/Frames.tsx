import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api,
  fileUrl,
  type AssetImageBatchStatus,
  type Chapter,
  type Entity,
  type FrameTaskIndex,
  type FrameType,
  type Project,
  type Shot,
  type TaskListItem,
} from '../lib/api'
import Lightbox from '../Lightbox'
import { confirmOverwrite } from '../lib/confirmOverwrite'

const FRAMES: { key: FrameType; label: string }[] = [
  { key: 'key', label: '关键帧' },
]

type FrameState = { fileId: string | null; busy: boolean; stage: string; error: string }
const emptyFrame = (): FrameState => ({ fileId: null, busy: false, stage: '', error: '' })

type FrameBatchView = { batchId: string; done: number; total: number; status: string }
type FrameBatchItemView = {
  shot_id: string
  name?: string
  status: string
  stage?: 'queued' | 'preparing' | 'prompt' | 'image' | 'done' | 'failed' | 'cancelled'
  error?: string
}
type StoredFrameBatch = { projectId: string; batchId: string }

const FRAME_BATCH_STORAGE_KEY = 'shotcat.frames.active-batch'
const ACTIVE_TASK_STATUSES = new Set(['pending', 'running', 'streaming'])
const ACTIVE_BATCH_STATUSES = new Set(['queued', 'running', 'cancelling'])

/** 用服务端时间比较同一画面的任务；时间相同优先采用刚返回的任务。 */
const latestFrameTask = (current: TaskListItem | undefined, incoming: TaskListItem | undefined) => {
  if (!current) return incoming
  if (!incoming) return current
  const currentTime = current.updated_at_ts ?? current.created_at_ts ?? 0
  const incomingTime = incoming.updated_at_ts ?? incoming.created_at_ts ?? 0
  return incomingTime >= currentTime ? incoming : current
}

/** 合并服务端索引，同时保留尚未被任务列表读到的本地活跃任务。 */
const mergeFrameTaskIndexes = (current: FrameTaskIndex, incoming: FrameTaskIndex): FrameTaskIndex => {
  const merged: FrameTaskIndex = {}
  for (const [shotId, frameTypes] of Object.entries(incoming)) merged[shotId] = { ...frameTypes }
  for (const [shotId, frameTypes] of Object.entries(current)) {
    for (const frameType of FRAMES.map((frame) => frame.key)) {
      const task = frameTypes[frameType]
      if (!task || !ACTIVE_TASK_STATUSES.has(task.status)) continue
      ;(merged[shotId] ||= {})[frameType] = latestFrameTask(task, merged[shotId]?.[frameType])
    }
  }
  return merged
}

const taskStage = (task: Pick<TaskListItem, 'status' | 'progress'>) =>
  task.status === 'pending' ? '等待生成…' : `生成画面… ${task.progress || 0}%`

const frameStatusLabel = (status: string | undefined, progress: number | undefined, hasImage: boolean) => {
  if (status === 'queued') return '排队中'
  if (status === 'pending') return '等待生成'
  if (status === 'running' || status === 'streaming') return `生成中 ${progress || 0}%`
  if (status === 'failed') return '生成失败'
  if (status === 'cancelled') return '已停止'
  if (status === 'succeeded' || hasImage) return '已生成'
  return ''
}

/** 把批次内部阶段转换成镜头级执行概况。 */
const frameBatchStageLabel = (item: FrameBatchItemView) => {
  const name = item.name || item.shot_id
  if (item.stage === 'prompt') return `${name}提示词生成`
  if (item.stage === 'image') return `${name}图像生成`
  if (item.status === 'succeeded' || item.stage === 'done') return `${name}图像已完成`
  if (item.status === 'failed' || item.stage === 'failed') return `${name}生成失败`
  if (item.status === 'cancelled' || item.stage === 'cancelled') return `${name}已停止`
  if (item.status === 'running' || item.stage === 'preparing') return `${name}准备生成`
  return `${name}等待生成`
}

const readStoredFrameBatch = (): StoredFrameBatch | null => {
  try {
    return JSON.parse(localStorage.getItem(FRAME_BATCH_STORAGE_KEY) || 'null') as StoredFrameBatch | null
  } catch {
    return null
  }
}

const rememberFrameBatch = (value: StoredFrameBatch) =>
  localStorage.setItem(FRAME_BATCH_STORAGE_KEY, JSON.stringify(value))

const forgetFrameBatch = (batchId: string) => {
  const stored = readStoredFrameBatch()
  if (!stored || stored.batchId === batchId) localStorage.removeItem(FRAME_BATCH_STORAGE_KEY)
}

const stripReferenceLines = (text: string) =>
  String(text || '')
    .split('\n')
    .filter((line) => !/^(角色参考|场景参考|道具参考|参考)：/.test(line.trim()))
    .join('\n')
    .trim()

export default function Frames({ project }: { project: Project | null }) {
  const [params, setParams] = useSearchParams()
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [shots, setShots] = useState<Shot[]>([])
  const [sel, setSel] = useState<Shot | null>(null)
  const [frames, setFrames] = useState<Record<FrameType, FrameState>>({
    first: emptyFrame(), key: emptyFrame(), last: emptyFrame(),
  })
  const [cast, setCast] = useState<Entity[]>([])
  const [scenes, setScenes] = useState<Entity[]>([])
  const [lb, setLb] = useState<string | null>(null)
  const [detail, setDetail] = useState<any>(null) // 镜头详情(含真实关键帧提示词)
  const [promptDrafts, setPromptDrafts] = useState<Partial<Record<FrameType, string>>>({})
  const [openCh, setOpenCh] = useState<Record<string, boolean>>({}) // 镜头列表按集折叠
  const [thumbs, setThumbs] = useState<Record<string, Partial<Record<FrameType, string>>>>({}) // 镜头缩略图索引
  const [batch, setBatch] = useState<FrameBatchView | null>(null)
  const [batchItemStatuses, setBatchItemStatuses] = useState<Record<string, string>>({})
  const [batchItems, setBatchItems] = useState<FrameBatchItemView[]>([])
  const [frameTasks, setFrameTasks] = useState<FrameTaskIndex>({})
  const [exporting, setExporting] = useState(false)

  // 当前选中镜头 id 的实时引用：异步链回写前用它校验镜头未被切走
  const selRef = useRef<string | null>(null)
  useEffect(() => { selRef.current = sel?.id ?? null }, [sel])
  // 卸载时置位，正在轮询的任务据此停止
  // 挂载时重置：StrictMode(dev) 模拟卸载会把 ref 置 true 且跨挂载保留，不重置则轮询秒取消
  const cancelledRef = useRef(false)
  const ownedTaskIdsRef = useRef(new Set<string>())
  const resumedTaskIdsRef = useRef(new Set<string>())
  const watchedBatchIdsRef = useRef(new Set<string>())
  const refreshedBatchItemsRef = useRef(new Set<string>())
  const autoStartedBatchRef = useRef('')
  const submittingBatchRef = useRef(false)
  const frameTasksRef = useRef<FrameTaskIndex>({})
  const thumbsRef = useRef<Record<string, Partial<Record<FrameType, string>>>>({})
  useEffect(() => { cancelledRef.current = false; return () => { cancelledRef.current = true } }, [])
  useEffect(() => { thumbsRef.current = thumbs }, [thumbs])

  /** 同步更新 state 与 ref，让镜头切换无需等待下一轮网络读取即可恢复状态。 */
  const updateFrameTasks = useCallback((updater: (current: FrameTaskIndex) => FrameTaskIndex) => {
    setFrameTasks((current) => {
      const next = updater(current)
      frameTasksRef.current = next
      return next
    })
  }, [])

  /** 服务端结果是事实来源，但提交后尚未可见的活跃任务不能被一次读取清掉。 */
  const mergeServerFrameTasks = useCallback((incoming: FrameTaskIndex) => {
    updateFrameTasks((current) => mergeFrameTaskIndexes(current, incoming))
  }, [updateFrameTasks])

  useEffect(() => {
    if (!project) return
    api.entities('character', project.id).then(setCast).catch(() => {})
    api.entities('scene', project.id).then(setScenes).catch(() => {})
    api.frameIndex().then(setThumbs).catch(() => {})
    api.frameTaskIndex().then(mergeServerFrameTasks).catch(() => {})
    api.chapters(project.id).then((cs) => {
      setChapters(cs)
      if (!cs.length) return
      // 载入全部章节的镜头（深链 ?shot= 可能指向第 2 集及以后的镜头）
      Promise.all([
        Promise.all(cs.map((c) => api.shots(c.id).catch(() => []))),
        api.shotDetails().catch(() => ({})),
      ]).then(([perCh, details]) => {
        const merged = perCh.flat().map((x) => {
          const d = (details as Record<string, any>)[x.id]
          return d ? { ...x, camera_shot: d.camera_shot, duration: d.duration } : x
        })
        setShots(merged)
        const want = params.get('shot')
        const target = merged.find((x) => x.id === want) ?? merged[0] ?? null
        setSel(target)
        // 默认只展开选中镜头所在的集；已手动开合过的保持原状
        const focusCh = target?.chapter_id ?? cs[0].id
        setOpenCh((o) => {
          const n = { ...o }
          cs.forEach((c) => { if (n[c.id] === undefined) n[c.id] = c.id === focusCh })
          if (want && target) n[focusCh] = true // 深链指定的镜头一定展开可见
          return n
        })
      })
    }).catch(() => {})
  }, [project?.id, params, mergeServerFrameTasks])

  const resumeFrameTask = useCallback(async (shotId: string, ft: FrameType, task: TaskListItem) => {
    if (ownedTaskIdsRef.current.has(task.task_id) || resumedTaskIdsRef.current.has(task.task_id)) return
    resumedTaskIdsRef.current.add(task.task_id)
    setFrames((prev) => ({
      ...prev,
      [ft]: { ...prev[ft], busy: true, error: '', stage: taskStage(task) },
    }))
    try {
      const status = await api.pollTask(
        task.task_id,
        (progress) => {
          if (selRef.current === shotId) {
            setFrames((prev) => ({
              ...prev,
              [ft]: { ...prev[ft], busy: true, stage: `生成画面… ${progress}%` },
            }))
          }
          updateFrameTasks((current) => ({
            ...current,
            [shotId]: {
              ...current[shotId],
              [ft]: { ...(current[shotId]?.[ft] || task), status: 'running', progress },
            },
          }))
        },
        120,
        () => cancelledRef.current,
      )
      if (cancelledRef.current) return
      updateFrameTasks((current) => ({
        ...current,
        [shotId]: { ...current[shotId], [ft]: { ...task, ...status } },
      }))
      if (status.status === 'succeeded') {
        const imgs = await api.frameImages(shotId)
        const hit = imgs.find((image) => image.frame_type === ft)
        if (!hit?.file_id) throw new Error('任务完成但未返回图片（模型未产出）')
        setThumbs((current) => ({
          ...current,
          [shotId]: { ...current[shotId], [ft]: hit.file_id! },
        }))
        if (selRef.current === shotId) {
          setFrames((prev) => ({
            ...prev,
            [ft]: { ...prev[ft], busy: false, stage: '', error: '', fileId: hit.file_id },
          }))
        }
      } else {
        const result = await api.taskResult(task.task_id).catch(() => null)
        if (selRef.current === shotId) {
          setFrames((prev) => ({
            ...prev,
            [ft]: {
              ...prev[ft],
              busy: false,
              stage: '',
              error: result?.error || (status.status === 'cancelled' ? '生成已停止' : '生成失败'),
            },
          }))
        }
      }
    } catch (error: any) {
      if (selRef.current === shotId) {
        setFrames((prev) => ({
          ...prev,
          [ft]: { ...prev[ft], busy: false, stage: '', error: error?.message || '生成失败' },
        }))
      }
    } finally {
      resumedTaskIdsRef.current.delete(task.task_id)
    }
  }, [updateFrameTasks])

  // 选中镜头 → 同时载入已有图片和后端持久化的最新生图任务。
  const loadFrames = useCallback(async (shotId: string) => {
    const knownTask = frameTasksRef.current[shotId]?.key
    const knownFileId = thumbsRef.current[shotId]?.key ?? null
    const initial: Record<FrameType, FrameState> = {
      first: emptyFrame(), key: { ...emptyFrame(), fileId: knownFileId }, last: emptyFrame(),
    }
    if (knownTask && ACTIVE_TASK_STATUSES.has(knownTask.status)) {
      initial.key = { ...initial.key, busy: true, stage: taskStage(knownTask) }
    }
    setFrames(initial)
    try {
      const [imgs, taskIndex] = await Promise.all([
        api.frameImages(shotId),
        api.frameTaskIndex().catch(() => null),
      ])
      if (selRef.current !== shotId) return // 已切换镜头，丢弃过期响应
      if (taskIndex) mergeServerFrameTasks(taskIndex)
      const next: Record<FrameType, FrameState> = {
        first: emptyFrame(), key: { ...emptyFrame(), fileId: knownFileId }, last: emptyFrame(),
      }
      for (const image of imgs) {
        if (image.frame_type in next) next[image.frame_type] = { ...emptyFrame(), fileId: image.file_id }
      }
      const task = latestFrameTask(knownTask, taskIndex?.[shotId]?.key)
      if (task && ACTIVE_TASK_STATUSES.has(task.status)) {
        next.key = { ...next.key, busy: true, stage: taskStage(task), error: '' }
      }
      setFrames(next)
      if (task && ACTIVE_TASK_STATUSES.has(task.status)) {
        void resumeFrameTask(shotId, 'key', task)
      } else if (task && (task.status === 'failed' || task.status === 'cancelled')) {
        const result = await api.taskResult(task.task_id).catch(() => null)
        if (selRef.current === shotId) {
          setFrames((prev) => ({
            ...prev,
            key: {
              ...prev.key,
              error: result?.error || (task.status === 'cancelled' ? '生成已停止' : '生成失败'),
            },
          }))
        }
      }
    } catch {
      // 页面仍可继续使用；下一次切换镜头会重试恢复。
    }
  }, [mergeServerFrameTasks, resumeFrameTask])

  useEffect(() => {
    if (!sel) return
    const shotId = sel.id
    setPromptDrafts({})
    loadFrames(shotId)
    api.shotDetail(shotId).then((d) => { if (selRef.current === shotId) setDetail(d) })
  }, [sel, loadFrames])

  const setFrame = (ft: FrameType, patch: Partial<FrameState>) =>
    setFrames((prev) => ({ ...prev, [ft]: { ...prev[ft], ...patch } }))

  async function generate(ft: FrameType) {
    if (!sel) return
    if (frames[ft].busy) return // 该帧正在生成，防重入
    if (frames[ft].fileId && !confirmOverwrite({
      step: `重新生成${FRAMES.find((frame) => frame.key === ft)?.label || '镜头画面'}`,
      replaces: ['当前镜头图片', '总览页中展示的对应画面'],
      consequence: '原画面将不再作为当前结果使用，已经完成的其他镜头不受影响。',
    })) return
    const shotId = sel.id
    const shot = sel
    // 已保存或正在编辑的提示词是用户可控的唯一来源；参考图约束只临时用于本次生图。
    const savedPrompt = String(promptDrafts[ft] ?? detail?.key_frame_prompt ?? '').trim()
    const alive = () => selRef.current === shotId // 镜头未被切走才回写 UI
    const cancelled = () => cancelledRef.current
    let imageTaskId = ''
    setFrame(ft, { busy: true, error: '', stage: '生成提示词…' })
    try {
      // 1) 基础提示词（失败/空则退回剧本摘录构造）
      let prompt = savedPrompt
      if (!prompt) {
        try {
          const ptask = await api.createFramePromptTask(shotId, ft)
          const ps = await api.pollTask(ptask, undefined, 60, cancelled)
          if (ps.status === 'succeeded') {
            const r = await api.taskResult(ptask)
            prompt = (r.result?.prompt || '').trim()
          }
        } catch {
          /* 降级到摘录 */
        }
      }
      if (!prompt) {
        prompt = [shot.camera_shot, shot.title, shot.script_excerpt].filter(Boolean).join('，').slice(0, 300)
      }
      if (!prompt) throw new Error('无可用提示词（该镜头缺少剧本摘录）')

      // 2) 生成图（target_ratio 必填；503=无图像模型 会在此同步抛出）
      // 带上镜头关联的造型图作参考图（角色→场景→道具）——跨镜一致性的关键
      const refs = await api.frameRefs(shotId, project?.id)
      const finalBasePrompt = (savedPrompt || stripReferenceLines(prompt)) + api.refGuard(refs)
      const rendered = savedPrompt ? null : await api.renderFramePrompt(shotId, ft, finalBasePrompt, refs).catch(() => null)
      const finalPrompt = (rendered?.rendered_prompt || finalBasePrompt).trim()
      // 仅在系统首次生成提示词时显示结果；用户已有提示词时绝不把附加约束回写到编辑框。
      if (alive() && !savedPrompt) setPromptDrafts((m) => ({ ...m, [ft]: finalPrompt }))
      if (alive()) setFrame(ft, { stage: refs.length ? `生成画面…（${refs.length} 张参考图）` : '生成画面…' })
      const ratio = project?.default_video_ratio || '9:16'
      const itask = await api.createFrameImageTask(shotId, ft, finalPrompt, ratio, refs)
      imageTaskId = itask
      ownedTaskIdsRef.current.add(itask)
      const pendingTask: TaskListItem = {
        task_id: itask,
        task_kind: 'image_generation',
        status: 'pending',
        progress: 0,
        created_at_ts: Date.now() / 1000,
        relation_type: 'shot_frame_image',
        navigate_relation_entity_id: shotId,
      }
      updateFrameTasks((current) => ({
        ...current,
        [shotId]: { ...current[shotId], [ft]: pendingTask },
      }))
      const is = await api.pollTask(itask, (p) => {
        if (alive()) setFrame(ft, { stage: `生成画面… ${p}%` })
        updateFrameTasks((current) => ({
          ...current,
          [shotId]: {
            ...current[shotId],
            [ft]: { ...(current[shotId]?.[ft] || pendingTask), status: 'running', progress: p },
          },
        }))
      }, 120, cancelled)
      updateFrameTasks((current) => ({
        ...current,
        [shotId]: { ...current[shotId], [ft]: { ...(current[shotId]?.[ft] || pendingTask), ...is } },
      }))
      if (is.status !== 'succeeded') {
        const r = await api.taskResult(itask).catch(() => null)
        throw new Error(r?.error || `生成${is.status === 'cancelled' ? '已取消' : '失败'}`)
      }

      // 3) 取回图片（占位行 file_id 可能为 null → 视为失败）
      const imgs = await api.frameImages(shotId)
      const hit = imgs.find((im) => im.frame_type === ft)
      if (!hit?.file_id) throw new Error('任务完成但未返回图片（模型未产出）')
      // 缩略图按镜头 id 记录，与当前选中无关，切走了也更新
      setThumbs((m) => ({ ...m, [shotId]: { ...m[shotId], [ft]: hit.file_id! } }))
      // 镜头已切走：结果已落库，下次选回该镜头 loadFrames 会取到；此处不再回写 UI
      if (!alive()) return
      setFrame(ft, { busy: false, stage: '', fileId: hit.file_id })
      api.shotDetail(shotId).then((d) => { if (selRef.current === shotId) setDetail(d) }) // 刷新真实帧提示词

    } catch (e: any) {
      if (imageTaskId) {
        updateFrameTasks((current) => ({
          ...current,
          [shotId]: {
            ...current[shotId],
            [ft]: { ...(current[shotId]?.[ft] || { task_id: imageTaskId, progress: 0 }), status: 'failed' },
          },
        }))
      }
      if (alive()) setFrame(ft, { busy: false, stage: '', error: e?.message || '生成失败' })
    } finally {
      if (imageTaskId) ownedTaskIdsRef.current.delete(imageTaskId)
    }
  }

  const applyFrameBatchStatus = useCallback((batchId: string, status: AssetImageBatchStatus) => {
    setBatch({
      batchId,
      done: status.succeeded + status.failed + status.cancelled,
      total: status.total,
      status: status.status,
    })
    const itemStatuses: Record<string, string> = {}
    for (const item of status.items || []) {
      if (item.shot_id) itemStatuses[item.shot_id] = item.status
    }
    setBatchItemStatuses(itemStatuses)
    setBatchItems((status.items || []) as FrameBatchItemView[])
  }, [])

  /** 批次中单个镜头完成后立即取回图片，不等待整个批次结束才刷新画面。 */
  const refreshCompletedBatchItems = useCallback(async (batchId: string, status: AssetImageBatchStatus) => {
    const completed = (status.items || []).filter((item) =>
      item.shot_id && (item.status === 'succeeded' || item.stage === 'done'),
    ) as FrameBatchItemView[]
    await Promise.all(completed.map(async (item) => {
      const refreshKey = `${batchId}:${item.shot_id}`
      if (refreshedBatchItemsRef.current.has(refreshKey)) return
      refreshedBatchItemsRef.current.add(refreshKey)
      try {
        const images = await api.frameImages(item.shot_id)
        const hit = images.find((image) => image.frame_type === 'key' && image.file_id)
        if (!hit?.file_id) {
          refreshedBatchItemsRef.current.delete(refreshKey)
          return
        }
        setThumbs((current) => ({
          ...current,
          [item.shot_id]: { ...current[item.shot_id], key: hit.file_id! },
        }))
        if (selRef.current === item.shot_id) {
          setFrames((current) => ({
            ...current,
            key: { ...current.key, busy: false, stage: '', error: '', fileId: hit.file_id },
          }))
        }
      } catch {
        refreshedBatchItemsRef.current.delete(refreshKey)
      }
    }))
  }, [])

  const watchFrameBatch = useCallback(async (batchId: string) => {
    if (watchedBatchIdsRef.current.has(batchId)) return
    watchedBatchIdsRef.current.add(batchId)
    try {
      const finalStatus = await api.pollFrameImageBatch(
        batchId,
        (status) => {
          applyFrameBatchStatus(batchId, status)
          void refreshCompletedBatchItems(batchId, status)
        },
        () => cancelledRef.current,
      )
      if (!finalStatus || cancelledRef.current) return
      applyFrameBatchStatus(batchId, finalStatus)
      await refreshCompletedBatchItems(batchId, finalStatus)
    } catch {
      // 后端重启后内存队列可能不存在；已完成的单项任务仍会从任务表恢复。
      if (!cancelledRef.current) {
        setBatch(null)
        setBatchItems([])
      }
    } finally {
      watchedBatchIdsRef.current.delete(batchId)
      if (cancelledRef.current) return
      forgetFrameBatch(batchId)
      api.frameIndex().then(setThumbs).catch(() => {})
      api.frameTaskIndex().then(mergeServerFrameTasks).catch(() => {})
      if (selRef.current) loadFrames(selRef.current)
    }
  }, [applyFrameBatchStatus, loadFrames, mergeServerFrameTasks, refreshCompletedBatchItems])

  useEffect(() => {
    if (!project) return
    const stored = readStoredFrameBatch()
    if (!stored || stored.projectId !== project.id) return
    void watchFrameBatch(stored.batchId)
  }, [project?.id, watchFrameBatch])

  async function generateBatchFrames(chapterId?: string) {
    if (!project || submittingBatchRef.current || (batch && ACTIVE_BATCH_STATUSES.has(batch.status)) || !shots.length) return
    submittingBatchRef.current = true
    const ft: FrameType = 'key'
    try {
      const stored = readStoredFrameBatch()
      if (stored?.projectId === project.id) {
        const storedStatus = await api.frameImageBatchStatus(stored.batchId).catch(() => null)
        if (storedStatus && ACTIVE_BATCH_STATUSES.has(storedStatus.status)) {
          applyFrameBatchStatus(stored.batchId, storedStatus)
          void watchFrameBatch(stored.batchId)
          return
        }
        forgetFrameBatch(stored.batchId)
      }
      const ratio = project.default_video_ratio || '9:16'
      const idx = await api.frameIndex().catch(() => thumbs)
      const queue = shots.filter((shot) => {
        if (chapterId && shot.chapter_id !== chapterId) return false
        const f = idx[shot.id]
        return !f?.key
      })
      if (!queue.length) {
        alert('当前列表没有缺失画面的镜头')
        return
      }
      setSel(queue[0])
      setBatch({ batchId: '', done: 0, total: queue.length, status: 'queued' })
      setBatchItems(queue.map((shot) => ({
        shot_id: shot.id,
        name: `镜头 ${String(shot.index).padStart(2, '0')} · ${shot.title || '未命名'}`,
        status: 'queued',
        stage: 'queued',
      })))
      const items = await Promise.all(queue.map(async (shot) => {
        const refs = await api.frameRefs(shot.id, project.id).catch(() => [])
        return {
          shot_id: shot.id,
          name: `镜头 ${String(shot.index).padStart(2, '0')} · ${shot.title || '未命名'}`,
          frame_type: ft,
          images: refs,
        }
      }))
      const created = await api.createFrameImageBatch(items, ratio)
      rememberFrameBatch({ projectId: project.id, batchId: created.batch_id })
      setBatch({ batchId: created.batch_id, done: 0, total: created.total, status: 'queued' })
      await watchFrameBatch(created.batch_id)
    } catch (error: any) {
      setBatch(null)
      setBatchItems([])
      alert(error?.message || '批量生成任务提交失败')
    } finally {
      submittingBatchRef.current = false
    }
  }

  /** 从分镜页进入时自动启动对应章节，并移除一次性参数防止刷新重复提交。 */
  useEffect(() => {
    const chapterId = params.get('generate')
    if (!project || !chapterId || !shots.some((shot) => shot.chapter_id === chapterId)) return
    const requestKey = `${project.id}:${chapterId}`
    if (autoStartedBatchRef.current === requestKey) return
    autoStartedBatchRef.current = requestKey
    const next = new URLSearchParams(params)
    next.delete('generate')
    setParams(next, { replace: true })
    setOpenCh((current) => ({ ...current, [chapterId]: true }))
    void generateBatchFrames(chapterId)
    // generateBatchFrames 只由一次性 URL 参数触发；ref 与参数移除共同阻止重复提交。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, shots, params, setParams])

  async function stopFrameBatch() {
    if (!batch?.batchId || !ACTIVE_BATCH_STATUSES.has(batch.status)) return
    try {
      const status = await api.cancelFrameImageBatch(batch.batchId)
      applyFrameBatchStatus(batch.batchId, status)
    } catch (error: any) {
      alert(error?.message || '停止批量生成失败')
    }
  }

  async function exportKeyframes() {
    if (!project || exporting) return
    setExporting(true)
    try {
      const response = await api.exportProjectKeyframes(project.id)
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(payload?.message || `导出失败 ${response.status}`)
      }
      const contentDisposition = response.headers.get('Content-Disposition') || ''
      const encodedName = /filename\*=UTF-8''([^;]+)/.exec(contentDisposition)?.[1]
      const filename = encodedName ? decodeURIComponent(encodedName) : `${project.name || '项目'}_关键帧.zip`
      const blobUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(blobUrl)
    } catch (error: any) {
      alert(error?.message || '导出关键帧失败')
    } finally {
      setExporting(false)
    }
  }

  if (!project) return <div className="center">未找到项目 · 请先用 bridge 导入剧本</div>
  const batchActive = Boolean(batch && ACTIVE_BATCH_STATUSES.has(batch.status))
  const anyBusy = Object.values(frames).some((f) => f.busy) || batchActive

  const readyCount = frames.key.fileId ? 1 : 0

  return (
      <div className="work frames-page">
        <div className="work-head">
          <h1>画面工作台</h1>
        <div className="spacer" />
          <button className="btn ghost" disabled={exporting || !project} onClick={exportKeyframes}>
            {exporting ? '打包导出中…' : '批量导出关键帧'}
          </button>
          <button className="btn ghost" disabled={anyBusy || !shots.length} onClick={() => void generateBatchFrames()}>
            {batchActive ? `批量生成 ${batch?.done}/${batch?.total}` : '批量生成缺失画面'}
          </button>
          <button className="btn primary" disabled={anyBusy || !sel} onClick={() => generate('key')}>生成本镜关键帧</button>
        </div>

        {batch && (
          <section className="frame-execution" aria-live="polite">
            <div className="frame-execution-head">
              <div>
                <strong>执行概况</strong>
                <span>{batch.done}/{batch.total}</span>
              </div>
              <span className={`frame-execution-state is-${batch.status}`}>
                {batchActive ? '执行中' : batch.status === 'succeeded' ? '已完成' : batch.status === 'cancelled' ? '已停止' : '有失败项'}
              </span>
              {batchActive && <button type="button" className="btn ghost" onClick={() => void stopFrameBatch()}>停止</button>}
            </div>
            <div className="frame-execution-progress"><i style={{ width: `${batch.total ? Math.round((batch.done / batch.total) * 100) : 0}%` }} /></div>
            <div className="frame-execution-list">
              {batchItems.map((item) => (
                <div className={`frame-execution-item is-${item.status}`} key={item.shot_id}>
                  <span className="frame-execution-dot" />
                  <span>{frameBatchStageLabel(item)}</span>
                  {item.error && <small>{item.error}</small>}
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="canvas">
          <div className="fstrip">
            <div className="lbl">镜头 · {shots.length}</div>
            {chapters.map((c) => {
              const list = shots.filter((s) => s.chapter_id === c.id)
              if (!list.length) return null
              return (
                <div className="fs-grp" key={c.id}>
                  <div className="fs-ch" onClick={() => setOpenCh((o) => ({ ...o, [c.id]: !o[c.id] }))}>
                    <span className="ep-caret">{openCh[c.id] ? '▾' : '▸'}</span>
                    <span className="t">第 {c.index} 集</span>
                    <span className="n">{list.length}</span>
                  </div>
                  {openCh[c.id] && list.map((s) => {
                    const t = thumbs[s.id]
                    const tf = t?.key
                    const task = frameTasks[s.id]?.key
                    const statusText = frameStatusLabel(batchItemStatuses[s.id] || task?.status, task?.progress, !!tf)
                    return (
                      <div key={s.id} className={'fshot' + (sel?.id === s.id ? ' sel' : '') + (s.is_stale ? ' stale' : '')} onClick={() => setSel(s)}>
                        {tf ? (
                          <img className="th" src={fileUrl(tf)} alt="" loading="lazy" />
                        ) : (
                          <div className={'th' + (s.status === 'ready' ? ' done' : '')} />
                        )}
                        <div className="m">
                          <div className="t">{s.title || `镜头 ${s.index}`}</div>
                          <div className="s">
                            {String(s.index).padStart(2, '0')}{s.camera_shot ? ` · ${s.camera_shot}` : ''}{s.is_stale ? ' · 待重做' : statusText ? ` · ${statusText}` : ''}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>

          <div className="stage-col">
            <div className="stage-title">
              <div className="h">
                镜头 {sel?.index ?? '—'} · {sel?.title || '未选择'}
                <span>{(sel?.script_excerpt || '').slice(0, 30)}</span>
              </div>
            </div>

            {sel?.is_stale && (
              <div className="stale-notice" role="status">
                <strong>这个镜头使用了旧版上游内容</strong>
                <span>{sel.stale_reason || '剧本、项目规则或造型已变化，请重新确认镜头并生成画面。'}</span>
              </div>
            )}

            {/* 镜头属性 + 就绪度：并入中间的紧凑信息条 */}
            <div className="meta-bar">
              <span className="mi"><b>序号</b>{sel ? String(sel.index).padStart(2, '0') : '—'}</span>
              <span className="mi"><b>景别</b>{sel?.camera_shot || '—'}</span>
              <span className="mi"><b>时长</b>{sel?.duration ? `${sel.duration}s` : '—'}</span>
              <span className="mi"><b>状态</b>{sel?.status === 'ready' ? '就绪' : '待确认'}</span>
              <span className="spacer" />
              <span className="ready-badge">关键帧 {readyCount} / 1</span>
            </div>

            <div className="frame-workspace">
              <div className="frame-main">
                <div className="frames">
                  {FRAMES.map((f) => {
                    const st = frames[f.key]
                    return (
                      <div key={f.key} className={'frame' + (st.fileId ? ' filled' : '')}>
                        <div className="img">
                          {st.busy ? (
                            <div className="ph"><div className="plus">◔</div>{st.stage}</div>
                          ) : st.fileId ? (
                            <img className="zoomable" src={fileUrl(st.fileId)} alt={f.label} title="点击放大"
                              onClick={() => setLb(fileUrl(st.fileId!))}
                              style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                          ) : st.error ? (
                            <div className="ph" style={{ color: 'var(--danger)' }} title={st.error}>⚠ {st.error.slice(0, 24)}</div>
                          ) : (
                            <div className="ph"><div className="plus">＋</div>生成{f.label}</div>
                          )}
                        </div>
                        <div className="cap">
                          <span className="k">{f.label}</span>
                          {st.fileId ? (
                            <span className="tag" style={{ cursor: st.busy ? 'default' : 'pointer', opacity: st.busy ? 0.5 : 1 }}
                              onClick={st.busy ? undefined : () => generate(f.key)}>
                              {st.busy ? '生成中' : st.error ? '生成失败 · 重生成' : '重生成'}
                            </span>
                          ) : (
                            <button className="btn ghost" style={{ padding: '2px 9px', fontSize: 11 }} disabled={st.busy || !sel} onClick={() => generate(f.key)}>
                              {st.busy ? '生成中' : '生成'}
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* 生成依据：角色/场景 参考，横向并入中间 */}
                <div className="refs-row">
                  <div className="refs-group">
                    <div className="rg-h">角色设计 · 生成依据</div>
                    <div className="rg-list">
                      {cast.length === 0 && <div className="muted" style={{ fontSize: 12 }}>暂无角色 · 先在造型页设置</div>}
                      {cast.map((c) => (
                        <div className="ref-ent" key={c.id}>
                          {c.thumbnail ? (
                            <img src={c.thumbnail} alt={c.name} title="点击放大" onClick={() => setLb(c.thumbnail!)} />
                          ) : (
                            <div className="ref-empty">未生成</div>
                          )}
                          <div className="rn">{c.name}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="refs-group">
                    <div className="rg-h">场景设计 · 生成依据</div>
                    <div className="rg-list">
                      {scenes.length === 0 && <div className="muted" style={{ fontSize: 12 }}>暂无场景 · 先在造型页设置</div>}
                      {scenes.map((s) => (
                        <div className="ref-ent" key={s.id}>
                          {s.thumbnail ? (
                            <img src={s.thumbnail} alt={s.name} title="点击放大" onClick={() => setLb(s.thumbnail!)} />
                          ) : (
                            <div className="ref-empty">未生成</div>
                          )}
                          <div className="rn">{s.name}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <aside className="prompt prompt-side">
                <div className="ph"><span className="k">画面提示词</span></div>
                {(() => {
                  const map: [FrameType, string][] = [
                    ['key', promptDrafts.key ?? detail?.key_frame_prompt ?? ''],
                  ]
                  const labels: Partial<Record<FrameType, string>> = { key: '关键帧' }
                  return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {map.map(([ft, v]) => (
                        <div className="box" key={ft}>
                          <div className="prompt-row-head">
                            <span className="em">【{labels[ft]}】</span>
                            <button
                              className="btn ghost"
                              style={{ padding: '2px 9px', fontSize: 11 }}
                              disabled={!sel || frames[ft].busy}
                              onClick={() => generate(ft)}
                            >
                              {frames[ft].fileId ? '用此提示词重生成' : '用此提示词生成'}
                            </button>
                          </div>
                          <textarea
                            className="prompt-edit"
                            value={promptDrafts[ft] ?? v}
                            placeholder="输入关键帧画面提示词"
                            onChange={(e) => {
                              setPromptDrafts((m) => ({ ...m, [ft]: e.target.value }))
                            }}
                            onBlur={(e) => {
                              if (!sel) return
                              const value = e.target.value
                              api.updateShotDetail(sel.id, { key_frame_prompt: value })
                                .then(() => setDetail((d: any) => ({ ...d, key_frame_prompt: value })))
                                .catch((err) => alert(err?.message || '保存提示词失败'))
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  )
                })()}
              </aside>
            </div>
          </div>
        </div>
        <Lightbox url={lb} onClose={() => setLb(null)} />
      </div>
  )
}
