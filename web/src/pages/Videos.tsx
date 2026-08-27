import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api,
  fileUrl,
  type Chapter,
  type FrameType,
  type InitialModelConnection,
  type ModelSetupCapability,
  type Project,
  type Shot,
  type ShotVideoReadiness,
  type SupportedModelProvider,
  type TaskListItem,
  type VideoGenerationOptions,
  type VideoPromptPreview,
  type VideoReferenceMode,
  type VideoTaskIndex,
} from '../lib/api'

const ACTIVE = new Set(['pending', 'running', 'streaming'])
const CHECK_LABELS: Record<string, string> = {
  extraction_ready: '设定已确认',
  duration_ready: '镜头时长',
  prompt_ready: '视频提示词',
  reference_frames_ready: '参考画面',
  video_model_ready: '视频模型',
  provider_ready: '供应商连接',
  model_constraints_ready: '模型规格',
  no_active_video_task: '任务空闲',
}

const MODE_OPTIONS: { value: VideoReferenceMode; label: string; hint: string; requires: FrameType[] }[] = [
  { value: 'first_last_key', label: '多参考帧', hint: '首帧锁开场、尾帧锁落点，关键帧锁中段状态。', requires: ['first', 'last', 'key'] },
  { value: 'first_last', label: '首尾帧', hint: '明确起点和终点，让动作在两种稳定状态间自然完成。', requires: ['first', 'last'] },
  { value: 'key', label: '关键帧', hint: '关键帧只作为镜头中段视觉锚点，不等同于首帧。', requires: ['key'] },
  { value: 'first', label: '首帧', hint: '锁定 0 秒开场状态，结束画面由时间轴控制。', requires: ['first'] },
  { value: 'last', label: '尾帧', hint: '锁定结束目标状态，开场画面由时间轴控制。', requires: ['last'] },
  { value: 'text_only', label: '纯文字', hint: '不使用画面参考，一致性完全依赖提示词。', requires: [] },
]

function modeAvailable(mode: VideoReferenceMode, shotFrames: Partial<Record<FrameType, string>> | undefined) {
  const option = MODE_OPTIONS.find((item) => item.value === mode)
  return Boolean(option && option.requires.every((frameType) => shotFrames?.[frameType]))
}

function providerSupportsMode(options: VideoGenerationOptions | null, mode: VideoReferenceMode) {
  return !options?.supported_reference_modes.length || options.supported_reference_modes.includes(mode)
}

function bestMode(
  shotFrames: Partial<Record<FrameType, string>> | undefined,
  options: VideoGenerationOptions | null,
): VideoReferenceMode {
  return MODE_OPTIONS.find((item) => (
    item.value !== 'text_only'
    && providerSupportsMode(options, item.value)
    && modeAvailable(item.value, shotFrames)
  ))?.value || 'text_only'
}

const emptyConnection = (): InitialModelConnection => ({
  provider_key: 'minimax', base_url: '', api_key: '', model_name: 'MiniMax-H3',
})

const DEFAULT_VIDEO_MODELS: Record<string, string> = {
  minimax: 'MiniMax-H3',
  openai: 'sora-2',
}

function statusText(task: TaskListItem | undefined, hasVideo: boolean) {
  if (task?.status === 'pending') return '排队中'
  if (task?.status === 'running' || task?.status === 'streaming') return `生成中 ${task.progress || 0}%`
  if (task?.status === 'failed') return '生成失败'
  if (task?.status === 'cancelled') return '已停止'
  if (hasVideo || task?.status === 'succeeded') return '已生成'
  return '待生成'
}

export default function Videos({ project }: { project: Project | null }) {
  const [params, setParams] = useSearchParams()
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [shots, setShots] = useState<Shot[]>([])
  const [frames, setFrames] = useState<Record<string, Partial<Record<'first' | 'key' | 'last', string>>>>({})
  const [framesLoaded, setFramesLoaded] = useState(false)
  const [tasks, setTasks] = useState<VideoTaskIndex>({})
  const [selectedId, setSelectedId] = useState('')
  const [mode, setMode] = useState<VideoReferenceMode>('key')
  const [readiness, setReadiness] = useState<ShotVideoReadiness | null>(null)
  const [preview, setPreview] = useState<VideoPromptPreview | null>(null)
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState<ModelSetupCapability | null>(null)
  const [providers, setProviders] = useState<SupportedModelProvider[]>([])
  const [options, setOptions] = useState<VideoGenerationOptions | null>(null)
  const [resolution, setResolution] = useState('')
  const [connection, setConnection] = useState<InitialModelConnection>(emptyConnection)
  const [savingModel, setSavingModel] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const stoppedRef = useRef(false)
  const autoModeShotRef = useRef('')
  const requestedShot = params.get('shot') || ''

  const selected = useMemo(() => shots.find((shot) => shot.id === selectedId) || null, [shots, selectedId])
  const ratio = options?.allowed_ratios.includes(project?.default_video_ratio || '')
    ? project?.default_video_ratio || options?.default_ratio || '9:16'
    : options?.default_ratio || project?.default_video_ratio || '9:16'

  const loadShots = useCallback(async () => {
    if (!project) return
    const chapterRows = await api.chapters(project.id)
    const shotRows = (await Promise.all(chapterRows.map((chapter) => api.shots(chapter.id).catch(() => [])))).flat()
    setChapters(chapterRows)
    setShots(shotRows)
    setSelectedId((current) => {
      return shotRows.some((shot) => shot.id === current) ? current
        : shotRows.find((shot) => shot.id === requestedShot)?.id || shotRows[0]?.id || ''
    })
  }, [project?.id, requestedShot])

  const refreshTask = useCallback(async (shotId: string) => {
    const incoming = await api.videoTaskIndex()
    if (!stoppedRef.current) setTasks(incoming)
    const task = incoming[shotId]
    if (task?.status === 'succeeded') await loadShots()
    return task
  }, [loadShots])

  useEffect(() => {
    stoppedRef.current = false
    autoModeShotRef.current = ''
    setFramesLoaded(false)
    if (!project) return () => { stoppedRef.current = true }
    Promise.all([
      loadShots(),
      api.frameIndex().then((value) => { setFrames(value); setFramesLoaded(true) }),
      api.videoTaskIndex().then(setTasks),
      api.videoModelSetup().then(setModel),
      api.supportedModelProviders('video').then(setProviders),
      api.videoGenerationOptions().then((value) => {
        setOptions(value)
        setResolution(value.default_resolution || value.allowed_resolutions[0] || '')
      }).catch(() => null),
    ]).catch((cause) => setError(cause instanceof Error ? cause.message : '视频工作台加载失败'))
    return () => { stoppedRef.current = true }
  }, [project?.id, loadShots])

  useEffect(() => {
    const modeScope = `${selectedId}:${options?.provider || 'loading'}:${options?.model_id || ''}`
    if (!selectedId || !framesLoaded || autoModeShotRef.current === modeScope) return
    setMode(bestMode(frames[selectedId], options))
    autoModeShotRef.current = modeScope
  }, [selectedId, framesLoaded, frames, options])

  useEffect(() => {
    if (!selectedId || !framesLoaded) return
    let live = true
    if (requestedShot !== selectedId) setParams({ shot: selectedId }, { replace: true })
    setReadiness(null); setPreview(null); setPrompt(''); setError('')
    Promise.all([
      api.videoReadiness(selectedId, mode),
      api.previewVideoPrompt({ shot_id: selectedId, reference_mode: mode, ratio }),
    ]).then(([nextReadiness, nextPreview]) => {
      if (!live) return
      setReadiness(nextReadiness)
      setPreview(nextPreview)
      setPrompt(nextPreview.prompt)
    }).catch((cause) => {
      if (live) setError(cause instanceof Error ? cause.message : '镜头视频信息加载失败')
    })
    return () => { live = false }
  }, [selectedId, mode, ratio, requestedShot, setParams, framesLoaded])

  useEffect(() => {
    const task = tasks[selectedId]
    if (!selectedId || !task || !ACTIVE.has(task.status)) return
    let live = true
    const timer = window.setInterval(async () => {
      try {
        const next = await refreshTask(selectedId)
        if (!live || !next || ACTIVE.has(next.status)) return
        setBusy(false)
        setReadiness(await api.videoReadiness(selectedId, mode))
        if (next.status === 'failed') {
          const result = await api.taskResult(next.task_id).catch(() => null)
          setError(result?.error || '视频生成失败')
        }
      } catch {}
    }, 3000)
    return () => { live = false; window.clearInterval(timer) }
  }, [selectedId, tasks[selectedId]?.task_id, tasks[selectedId]?.status, mode, refreshTask])

  const chooseProvider = (key: string) => {
    const provider = providers.find((item) => item.key === key)
    setConnection({
      provider_key: key,
      base_url: provider?.default_base_url || '',
      api_key: '',
      model_name: DEFAULT_VIDEO_MODELS[key] || '',
    })
  }

  const saveModel = async () => {
    setSavingModel(true); setError('')
    try {
      const saved = await api.saveVideoModelSetup(connection)
      setModel(saved)
      const nextOptions = await api.videoGenerationOptions()
      setOptions(nextOptions)
      setResolution(nextOptions.default_resolution || nextOptions.allowed_resolutions[0] || '')
      if (selectedId) setReadiness(await api.videoReadiness(selectedId, mode))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '视频模型保存失败')
    } finally { setSavingModel(false) }
  }

  const generate = async () => {
    if (!selected || !readiness?.ready || !prompt.trim()) return
    setBusy(true); setError('')
    try {
      const taskId = await api.createVideoTask({
        shot_id: selected.id,
        reference_mode: mode,
        prompt: prompt.trim(),
        images: preview?.images || [],
        ratio,
        resolution: resolution || null,
      })
      setTasks((current) => ({
        ...current,
        [selected.id]: { task_id: taskId, status: 'pending', progress: 0, task_kind: 'video_generation', relation_entity_id: selected.id },
      }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '视频任务创建失败')
    } finally { setBusy(false) }
  }

  const cancel = async () => {
    const task = tasks[selectedId]
    if (!task) return
    setBusy(true)
    try {
      await api.cancelTask(task.task_id)
      await refreshTask(selectedId)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '停止任务失败')
    } finally { setBusy(false) }
  }

  if (!project) return <div className="center">请从作品库选择项目</div>
  const task = tasks[selectedId]
  const active = Boolean(task && ACTIVE.has(task.status))
  const selectedFrames = selected ? frames[selected.id] : undefined
  const monitorFrame = mode === 'last' ? selectedFrames?.last
    : mode === 'key' ? selectedFrames?.key
      : selectedFrames?.first || selectedFrames?.key || selectedFrames?.last
  const selectedMode = MODE_OPTIONS.find((item) => item.value === mode) || MODE_OPTIONS[MODE_OPTIONS.length - 1]
  const plan = preview?.execution_plan

  return (
    <div className="video-page">
      <aside className="video-shots" aria-label="镜头列表">
        <header><b>视频镜头</b><span>{shots.filter((shot) => shot.generated_video_file_id).length}/{shots.length}</span></header>
        {chapters.map((chapter) => (
          <section key={chapter.id}>
            <h2>{String(chapter.index).padStart(2, '0')} · {chapter.title}</h2>
            {shots.filter((shot) => shot.chapter_id === chapter.id).map((shot) => {
              const shotTask = tasks[shot.id]
              return <button type="button" key={shot.id} className={shot.id === selectedId ? 'on' : ''} onClick={() => setSelectedId(shot.id)}>
                <span className="video-shot-no">{String(shot.index).padStart(3, '0')}</span>
                <span className="video-shot-name">{shot.title || shot.script_excerpt || '未命名镜头'}</span>
                <em className={shot.generated_video_file_id ? 'done' : ACTIVE.has(shotTask?.status || '') ? 'run' : ''}>
                  {statusText(shotTask, Boolean(shot.generated_video_file_id))}
                </em>
              </button>
            })}
          </section>
        ))}
        {!shots.length && <p className="video-empty">请先在分镜页拆出镜头。</p>}
      </aside>

      <main className="video-stage">
        <header className="video-stage-head">
          <div><span>图像转视频</span><h1>{selected ? `镜头 ${String(selected.index).padStart(3, '0')}` : '未选择镜头'}</h1></div>
          {selected && <b>{selected.duration || '—'} 秒 · {ratio}</b>}
        </header>
        <div className="video-monitor">
          {selected?.generated_video_file_id ? (
            <video controls preload="metadata" src={fileUrl(selected.generated_video_file_id)} />
          ) : monitorFrame ? (
            <img src={fileUrl(monitorFrame)} alt="当前视频参考画面" />
          ) : (
            <div className="video-placeholder"><span aria-hidden="true">◇</span><b>当前模式没有参考画面</b><p>可选择纯文字，或先在画面页补齐所需帧。</p></div>
          )}
          {active && <div className="video-rendering"><i /><b>正在生成视频</b><span>{task.progress || 0}%</span></div>}
        </div>
        <div className="video-caption">
          <span>{selected?.generated_video_file_id ? '生成结果' : '视频参考画面'}</span>
          <p>{selected?.script_excerpt || selected?.description || '选择镜头后查看生成上下文。'}</p>
        </div>
        {plan && (
          <section className="video-plan" aria-label="视频执行计划">
            <header>
              <div><span>生成前执行概况</span><h2>{plan.generation_path_label}</h2></div>
              <b>{plan.target_duration_s} 秒完整时间轴</b>
            </header>
            <div className="video-state-pair">
              <article><span>0 秒起始状态</span><p>{plan.start_state}</p></article>
              <article><span>结束目标状态</span><p>{plan.end_state}</p></article>
            </div>
            {plan.references.length > 0 && <div className="video-reference-strip">
              {plan.references.map((reference) => <article key={`${reference.frame_type}-${reference.file_id}`}>
                <img src={fileUrl(reference.file_id)} alt={reference.title} />
                <div><b>{reference.title}</b><p>{reference.instruction}</p></div>
              </article>)}
            </div>}
            <div className="video-timeline">
              {plan.timeline.map((segment, index) => <article key={`${segment.start_s}-${segment.end_s}`}>
                <div className="video-time"><span>{segment.start_s.toFixed(segment.start_s % 1 ? 1 : 0)}</span><i /><span>{segment.end_s.toFixed(segment.end_s % 1 ? 1 : 0)}s</span></div>
                <div><b>{String(index + 1).padStart(2, '0')} · {segment.purpose}</b><p>{segment.action}</p><small>{segment.camera}</small><em>{segment.audio}</em></div>
              </article>)}
            </div>
            <footer><span>声音总则</span><p>{plan.audio_approach}</p></footer>
            {plan.warnings.map((warning) => <div className="video-plan-warning" key={warning}>{warning}</div>)}
          </section>
        )}
      </main>

      <aside className="video-controls">
        <header><span>生成设置</span><b>{statusText(task, Boolean(selected?.generated_video_file_id))}</b></header>

        {model && !model.ready ? (
          <section className="video-model-setup">
            <div className="video-section-title">连接视频模型</div>
            <p>视频模型按需配置，不影响文字和图片流程。API Key 只保存在本机数据库。</p>
            <label>供应商<select value={connection.provider_key} onChange={(event) => chooseProvider(event.target.value)}>
              {providers.map((provider) => <option key={provider.key} value={provider.key}>{provider.display_name}</option>)}
            </select></label>
            <label>模型 ID<input value={connection.model_name} placeholder="模型 ID 或 ep-…" onChange={(event) => setConnection((current) => ({ ...current, model_name: event.target.value }))} /></label>
            <label>API Key<input type="password" autoComplete="off" value={connection.api_key} onChange={(event) => setConnection((current) => ({ ...current, api_key: event.target.value }))} /></label>
            <label>接口地址<input value={connection.base_url} placeholder="使用供应商默认地址" onChange={(event) => setConnection((current) => ({ ...current, base_url: event.target.value }))} /></label>
            <button type="button" className="video-primary" disabled={savingModel || !connection.model_name.trim() || !connection.api_key.trim()} onClick={() => void saveModel()}>
              {savingModel ? '保存中…' : '保存并检查'}
            </button>
          </section>
        ) : (
          <>
            <section>
              <div className="video-section-title">参考方式</div>
              <div className="video-mode-tabs">
                {MODE_OPTIONS.map((option) => {
                  const frameReady = modeAvailable(option.value, selectedFrames)
                  const modelReady = providerSupportsMode(options, option.value)
                  const available = frameReady && modelReady
                  const missing = option.requires.filter((frameType) => !selectedFrames?.[frameType])
                  return <button
                    type="button"
                    key={option.value}
                    className={mode === option.value ? 'on' : ''}
                    disabled={!available}
                    title={!modelReady ? '当前视频模型不支持这种参考方式'
                      : !frameReady ? `缺少${missing.map((item) => ({ first: '首帧', last: '尾帧', key: '关键帧' })[item]).join('、')}`
                        : option.hint}
                    onClick={() => setMode(option.value)}
                  >{option.label}</button>
                })}
              </div>
              <p className="video-hint">{selectedMode.hint}</p>
            </section>
            {options && options.allowed_resolutions.length > 0 && <section>
              <div className="video-section-title">输出清晰度</div>
              <select className="video-resolution" value={resolution} onChange={(event) => setResolution(event.target.value)} disabled={active}>
                {options.allowed_resolutions.map((item) => <option value={item} key={item}>{item}</option>)}
              </select>
              <p className="video-hint">
                {options.min_seconds && options.max_seconds
                  ? `${options.model_name} 支持 ${options.min_seconds}–${options.max_seconds} 秒；参考帧模式会自动跟随输入画幅。`
                  : `清晰度由 ${options.model_name} 提供。`}
              </p>
            </section>}
            <section>
              <div className="video-section-title">准备检查</div>
              <div className="video-checks">
                {readiness?.checks.map((check) => <div key={check.key} className={check.ok ? 'ok' : 'bad'} title={check.message}>
                  <i>{check.ok ? '✓' : '!'}</i><span>{CHECK_LABELS[check.key] || check.key}</span><em>{check.message}</em>
                </div>)}
                {!readiness && <p>检查中…</p>}
              </div>
            </section>
            <section className="video-prompt">
              <div className="video-section-title">最终执行提示词</div>
              <p className="video-hint">已自动写入完整时间轴、起止状态、参考图职责和声音规则，可在提交前微调。</p>
              <textarea value={prompt} disabled={!selected || active} onChange={(event) => setPrompt(event.target.value)} placeholder="镜头动作、镜头运动、节奏与声音…" />
            </section>
            {error && <div className="video-error">{error}</div>}
            <div className="video-actions">
              {active ? <button type="button" className="video-stop" disabled={busy} onClick={() => void cancel()}>{busy ? '停止中…' : '停止生成'}</button>
                : <button type="button" className="video-primary" disabled={busy || !readiness?.ready || !prompt.trim()} onClick={() => void generate()}>
                  {busy ? '提交中…' : selected?.generated_video_file_id ? '重新生成视频' : '生成视频'}
                </button>}
            </div>
          </>
        )}
        {error && model && !model.ready && <div className="video-error">{error}</div>}
      </aside>
    </div>
  )
}
