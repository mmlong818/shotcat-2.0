import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api,
  findPipelineJob,
  forgetPipelineJob,
  PIPELINE_JOB_EVENT,
  readPipelineJobs,
  type AssetImageBatchStatus,
  type PipelineJobRecord,
  type PipelineJobStatus,
  type PipelineStep,
  type TaskListItem,
} from './lib/api'

const REFRESH_MS = 2500
const TERMINAL_BATCH_STATUSES = new Set(['succeeded', 'failed', 'cancelled'])

type PipelineActivity = PipelineJobRecord & {
  status: PipelineJobStatus['status'] | 'unavailable'
  cancelRequested?: boolean
}

type BatchKind = 'asset' | 'frame'
type BatchRegistration = {
  kind: BatchKind
  batchId: string
  route: string
  storageKeys: string[]
}
type BatchActivity = BatchRegistration & { state: AssetImageBatchStatus | null }

type CancelTarget =
  | { kind: 'pipeline'; jobId: string }
  | { kind: 'batch'; batchKind: BatchKind; batchId: string }
  | { kind: 'tasks'; taskIds: string[] }

type ActivityRow = {
  key: string
  label: string
  count: number
  progress: number | null
  status: string
  route: string
  cancelling: boolean
  error: boolean
  target: CancelTarget
}

const PIPELINE_LABELS: Record<PipelineStep, string> = {
  'extract-setup': '从剧本抽取设定',
  'visual-dict': '锁定视觉词典',
  'shot-breakdown': 'AI 拆分镜头',
  'unit-gen': '生成视听单元',
}

const PIPELINE_ROUTES: Record<PipelineStep, string> = {
  'extract-setup': '/script',
  'visual-dict': '/cast',
  'shot-breakdown': '/board',
  'unit-gen': '/board',
}

/** 把后端通用任务转换成用户能直接理解的步骤名称。 */
const taskLabel = (task: TaskListItem) => {
  if (task.task_kind === 'project_brain_extract') return '分析项目大脑'
  if (task.task_kind === 'shot_frame_prompt') return '生成镜头提示词'
  if (task.task_kind === 'image_generation') {
    return task.relation_type === 'shot_frame_image' ? '生成镜头图片' : '生成设定图片'
  }
  if (task.task_kind === 'video_generation') return '生成视频'
  if (task.task_kind.startsWith('script_')) return '处理剧本'
  return '执行后台任务'
}

/** 根据任务关联信息返回对应业务页面，供状态卡一键回跳。 */
const taskRoute = (task: TaskListItem) => {
  if (task.task_kind === 'project_brain_extract') return '/brain'
  if (task.task_kind === 'shot_frame_prompt' || task.relation_type === 'shot_frame_image') {
    const shotId = task.navigate_relation_entity_id
    return shotId ? `/frames?shot=${encodeURIComponent(shotId)}` : '/frames'
  }
  if (task.task_kind === 'image_generation') return '/cast'
  if (task.task_kind === 'video_generation') return '/gallery'
  if (task.task_kind.startsWith('script_')) return '/script'
  return '/overview'
}

/** 合并同类通用任务，同时保留全部任务编号供“停止”一次性撤销。 */
function taskRows(tasks: TaskListItem[]): ActivityRow[] {
  const groups = new Map<string, TaskListItem[]>()
  for (const task of tasks) {
    const key = `${taskLabel(task)}:${taskRoute(task).split('?')[0]}`
    groups.set(key, [...(groups.get(key) || []), task])
  }
  return Array.from(groups.entries()).map(([key, items]) => {
    const progress = Math.round(items.reduce((sum, item) => sum + (item.progress || 0), 0) / items.length)
    const cancelling = items.some((item) => item.cancel_requested)
    const queued = items.every((item) => item.status === 'pending')
    return {
      key,
      label: taskLabel(items[0]),
      count: items.length,
      progress,
      status: cancelling ? '停止中' : queued ? '排队中' : `${progress}%`,
      route: taskRoute(items[0]),
      cancelling,
      error: false,
      target: { kind: 'tasks', taskIds: items.map((item) => item.task_id) },
    }
  })
}

/** 读取各业务页保存的批量任务编号，让全局状态卡可以停止整条队列。 */
function readBatchRegistrations(): BatchRegistration[] {
  const records = new Map<string, BatchRegistration>()
  const add = (record: BatchRegistration) => {
    const key = `${record.kind}:${record.batchId}`
    const current = records.get(key)
    records.set(key, current ? { ...current, storageKeys: [...new Set([...current.storageKeys, ...record.storageKeys])] } : record)
  }
  for (let index = 0; index < localStorage.length; index++) {
    const storageKey = localStorage.key(index)
    if (!storageKey) continue
    const raw = localStorage.getItem(storageKey) || ''
    if (storageKey.startsWith('shotcat:assetImageBatch:') && raw) {
      add({ kind: 'asset', batchId: raw, route: '/cast', storageKeys: [storageKey] })
      continue
    }
    if (storageKey.startsWith('shotcat:frameImageBatch:')) {
      try {
        const value = JSON.parse(raw)
        if (value?.batchId) add({ kind: 'frame', batchId: value.batchId, route: '/board', storageKeys: [storageKey] })
      } catch {}
      continue
    }
    if (storageKey === 'shotcat.frames.active-batch') {
      try {
        const value = JSON.parse(raw)
        if (value?.batchId) add({ kind: 'frame', batchId: value.batchId, route: '/frames', storageKeys: [storageKey] })
      } catch {}
    }
  }
  return [...records.values()]
}

/** 仅清除仍指向当前批次的浏览器记录，避免误删刚创建的新批次。 */
function forgetBatchRegistration(batch: BatchRegistration) {
  for (const storageKey of batch.storageKeys) {
    const current = localStorage.getItem(storageKey)
    if (current?.includes(batch.batchId)) localStorage.removeItem(storageKey)
  }
}

/** 返回当前项目某一步 pipeline 是否仍有已登记的后台作业。 */
export function usePipelineJobActive(projectId: string | undefined, step: PipelineStep) {
  const [active, setActive] = useState(() => Boolean(findPipelineJob(projectId, step)))
  useEffect(() => {
    const sync = () => setActive(Boolean(findPipelineJob(projectId, step)))
    sync()
    window.addEventListener(PIPELINE_JOB_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(PIPELINE_JOB_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [projectId, step])
  return active
}

/** 在所有页面之上展示服务端任务，并提供统一回跳与停止操作。 */
export default function TaskActivity() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<TaskListItem[]>([])
  const [pipeline, setPipeline] = useState<PipelineActivity[]>([])
  const [batches, setBatches] = useState<BatchActivity[]>([])
  const [cancellingKeys, setCancellingKeys] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    let stopped = false
    let refreshing = false

    /** 并行刷新三类任务；单个服务临时失败时保留已有可见状态。 */
    const refresh = async () => {
      if (refreshing) return
      refreshing = true
      try {
        const jobs = readPipelineJobs()
        const batchRegistrations = readBatchRegistrations()
        const [nextTasks, nextPipeline, nextBatches] = await Promise.all([
          api.activeTasks().catch(() => null),
          Promise.all(jobs.map(async (job): Promise<PipelineActivity | null> => {
            try {
              const state = await api.pipelineJobStatus(job.jobId)
              if (state.status === 'done' || state.status === 'error' || state.status === 'cancelled') {
                forgetPipelineJob(job.jobId)
                return null
              }
              return { ...job, status: state.status, cancelRequested: state.cancel_requested }
            } catch (error) {
              if (error instanceof Error && error.message.includes('job not found')) {
                forgetPipelineJob(job.jobId)
                return null
              }
              return { ...job, status: 'unavailable' }
            }
          })),
          Promise.all(batchRegistrations.map(async (batch): Promise<BatchActivity | null> => {
            try {
              const state = batch.kind === 'asset'
                ? await api.assetImageBatchStatus(batch.batchId)
                : await api.frameImageBatchStatus(batch.batchId)
              if (TERMINAL_BATCH_STATUSES.has(state.status)) {
                forgetBatchRegistration(batch)
                return null
              }
              return { ...batch, state }
            } catch (error) {
              if (error instanceof Error && error.message.includes('404')) {
                forgetBatchRegistration(batch)
                return null
              }
              return { ...batch, state: null }
            }
          })),
        ])
        if (!stopped) {
          if (nextTasks) setTasks(nextTasks)
          setPipeline(nextPipeline.filter((job): job is PipelineActivity => job !== null))
          setBatches(nextBatches.filter((batch): batch is BatchActivity => batch !== null))
        }
      } finally {
        refreshing = false
      }
    }

    void refresh()
    const timer = window.setInterval(refresh, REFRESH_MS)
    window.addEventListener(PIPELINE_JOB_EVENT, refresh)
    window.addEventListener('storage', refresh)
    return () => {
      stopped = true
      window.clearInterval(timer)
      window.removeEventListener(PIPELINE_JOB_EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  const rows = useMemo(() => {
    const batchTaskIds = new Set(batches.flatMap((batch) => [
      batch.state?.current_task_id,
      ...(batch.state?.items || []).map((item) => item.task_id),
    ].filter((taskId): taskId is string => Boolean(taskId))))
    return [
      ...pipeline.map((job): ActivityRow => {
        const cancelling = Boolean(job.cancelRequested || job.status === 'cancelling')
        return {
          key: `pipeline:${job.jobId}`,
          label: PIPELINE_LABELS[job.step],
          count: 1,
          progress: null,
          status: cancelling
            ? '停止中'
            : job.status === 'queued'
              ? '排队中'
              : job.status === 'awaiting_confirmation'
                ? '等待确认'
                : job.status === 'unavailable'
                  ? '服务连接中断'
                  : '执行中',
          route: PIPELINE_ROUTES[job.step],
          cancelling,
          error: job.status === 'unavailable',
          target: { kind: 'pipeline', jobId: job.jobId },
        }
      }),
      ...batches.map((batch): ActivityRow => {
        const state = batch.state
        const finished = state ? state.succeeded + state.failed + state.cancelled : 0
        const progress = state?.total ? Math.round((finished / state.total) * 100) : null
        const cancelling = state?.status === 'cancelling'
        return {
          key: `batch:${batch.kind}:${batch.batchId}`,
          label: batch.kind === 'asset' ? '批量生成设定图片' : '批量生成镜头图片',
          count: Math.max(1, state ? state.queued + state.running : 1),
          progress,
          status: cancelling ? '停止中' : state ? `${finished}/${state.total}` : '服务连接中断',
          route: batch.route,
          cancelling,
          error: state === null,
          target: { kind: 'batch', batchKind: batch.kind, batchId: batch.batchId },
        }
      }),
      ...taskRows(tasks.filter((task) => !batchTaskIds.has(task.task_id))),
    ]
  }, [batches, pipeline, tasks])

  /** 根据行类型调用真实取消接口，并立即把本地状态推进到“停止中”。 */
  const cancelRow = async (row: ActivityRow) => {
    if (row.cancelling || cancellingKeys.has(row.key)) return
    if (!window.confirm(`停止“${row.label}”？已经完成的结果会保留。`)) return
    setCancellingKeys((current) => new Set(current).add(row.key))
    try {
      if (row.target.kind === 'pipeline') {
        const { jobId } = row.target
        const state = await api.cancelPipelineJob(jobId)
        if (state.status === 'cancelled') {
          forgetPipelineJob(jobId)
          setPipeline((current) => current.filter((job) => job.jobId !== jobId))
        } else {
          setPipeline((current) => current.map((job) =>
            job.jobId === jobId ? { ...job, status: state.status, cancelRequested: true } : job,
          ))
        }
      } else if (row.target.kind === 'batch') {
        const { batchId, batchKind } = row.target
        const state = batchKind === 'asset'
          ? await api.cancelAssetImageBatch(batchId)
          : await api.cancelFrameImageBatch(batchId)
        setBatches((current) => current.map((batch) =>
          batch.batchId === batchId && batch.kind === batchKind ? { ...batch, state } : batch,
        ))
      } else {
        const results = await Promise.allSettled(row.target.taskIds.map((taskId) => api.cancelTask(taskId)))
        const cancelledIds = new Set(row.target.taskIds.filter((_, index) => results[index].status === 'fulfilled'))
        setTasks((current) => current.map((task) =>
          cancelledIds.has(task.task_id) ? { ...task, cancel_requested: true } : task,
        ))
        const failed = results.filter((result) => result.status === 'rejected').length
        if (failed) throw new Error(`${failed} 项任务未能停止`)
      }
    } catch (error) {
      window.alert(error instanceof Error ? error.message : '停止任务失败')
    } finally {
      setCancellingKeys((current) => {
        const next = new Set(current)
        next.delete(row.key)
        return next
      })
    }
  }

  const total = rows.reduce((sum, row) => sum + row.count, 0)
  if (!rows.length) return null

  return (
    <aside className="task-activity" aria-live="polite" aria-label="正在执行的任务">
      <div className="task-activity-head">
        <span className="task-activity-spinner" />
        <strong>正在执行</strong>
        <span>{total} 项</span>
      </div>
      <div className="task-activity-list">
        {rows.map((row) => {
          const stopping = row.cancelling || cancellingKeys.has(row.key)
          return (
            <div className="task-activity-row" key={row.key}>
              <button type="button" className="task-activity-main" onClick={() => navigate(row.route)}>
                <span className="task-activity-name">{row.label}{row.count > 1 ? ` × ${row.count}` : ''}</span>
                <span className={row.error ? 'task-activity-state is-error' : 'task-activity-state'}>{stopping ? '停止中' : row.status}</span>
                {row.progress != null ? <span className="task-activity-bar"><i style={{ width: `${row.progress}%` }} /></span> : null}
              </button>
              <button type="button" className="task-activity-stop" disabled={stopping} onClick={() => void cancelRow(row)}>
                {stopping ? '停止中' : '停止'}
              </button>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
