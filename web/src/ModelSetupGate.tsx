import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type InitialModelConnection,
  type InitialModelSetupStatus,
  type ModelSetupCapability,
  type SupportedModelProvider,
} from './lib/api'

type Category = 'text' | 'image'
type Drafts = Record<Category, InitialModelConnection>

const OPENAI_DEFAULT_MODELS: Record<Category, string> = {
  text: 'gpt-5.6-sol',
  image: 'gpt-image-2',
}

/** 生成一类模型表单的默认值；OpenAI 使用已核对的官方模型 ID。 */
function defaultDraft(category: Category, providers: SupportedModelProvider[]): InitialModelConnection {
  const provider = providers.find((item) => item.key === 'openai') ?? providers[0]
  return {
    provider_key: provider?.key ?? '',
    base_url: provider?.default_base_url ?? '',
    api_key: '',
    model_name: provider?.key === 'openai' ? OPENAI_DEFAULT_MODELS[category] : '',
  }
}

/** 将网络或校验异常转换成用户能直接处理的短提示。 */
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '保存失败，请检查连接信息后重试'
}

function CapabilitySummary({ capability }: { capability: ModelSetupCapability }) {
  return (
    <div className="model-ready-summary">
      <span className="model-ready-check" aria-hidden="true">✓</span>
      <div>
        <strong>已经配置</strong>
        <p>{capability.provider_name} · {capability.model_name}</p>
      </div>
    </div>
  )
}

interface ModelConnectionCardProps {
  category: Category
  capability: ModelSetupCapability
  providers: SupportedModelProvider[]
  draft: InitialModelConnection
  disabled: boolean
  onChange: (next: InitialModelConnection) => void
}

/** 单类模型连接表单；文字和图片保持完全独立的供应商、模型与 Key。 */
function ModelConnectionCard({
  category,
  capability,
  providers,
  draft,
  disabled,
  onChange,
}: ModelConnectionCardProps) {
  const isText = category === 'text'
  const selectedProvider = providers.find((item) => item.key === draft.provider_key)

  const selectProvider = (providerKey: string) => {
    const provider = providers.find((item) => item.key === providerKey)
    onChange({
      ...draft,
      provider_key: providerKey,
      base_url: provider?.default_base_url ?? '',
      model_name: providerKey === 'openai' ? OPENAI_DEFAULT_MODELS[category] : '',
    })
  }

  return (
    <section className={`model-setup-card ${isText ? 'is-text' : 'is-image'}`} aria-labelledby={`model-${category}-title`}>
      <div className="model-card-head">
        <span className="model-card-mark" aria-hidden="true">{isText ? '文' : '图'}</span>
        <div>
          <h2 id={`model-${category}-title`}>{isText ? '文字模型' : '图像模型'}</h2>
          <p>{isText ? '负责剧本拆解与镜头提示词' : '负责角色设定与镜头画面'}</p>
        </div>
        <span className={`model-state ${capability.ready ? 'ready' : ''}`}>
          {capability.ready ? '可用' : '待配置'}
        </span>
      </div>

      {capability.ready ? <CapabilitySummary capability={capability} /> : (
        <div className="model-fields">
          <label className="model-field">
            <span>服务商</span>
            <select
              value={draft.provider_key}
              disabled={disabled}
              onChange={(event) => selectProvider(event.target.value)}
            >
              {providers.map((provider) => (
                <option key={provider.key} value={provider.key}>{provider.display_name}</option>
              ))}
            </select>
          </label>

          <label className="model-field">
            <span>模型 ID</span>
            <input
              value={draft.model_name}
              disabled={disabled}
              spellCheck={false}
              placeholder={isText ? '从服务商控制台复制文字模型 ID' : '从服务商控制台复制图像模型 ID'}
              onChange={(event) => onChange({ ...draft, model_name: event.target.value })}
            />
          </label>

          <label className="model-field">
            <span>API Key</span>
            <input
              name={`${category}-api-key`}
              type="password"
              value={draft.api_key}
              disabled={disabled}
              autoComplete="off"
              spellCheck={false}
              placeholder={selectedProvider?.requires_api_key === false ? '此服务商无需 Key' : '粘贴 API Key'}
              onChange={(event) => onChange({ ...draft, api_key: event.target.value })}
            />
          </label>

          <label className="model-field model-field-wide">
            <span>API 地址</span>
            <input
              type="url"
              value={draft.base_url}
              disabled={disabled}
              spellCheck={false}
              placeholder="https://api.example.com/v1"
              onChange={(event) => onChange({ ...draft, base_url: event.target.value })}
            />
          </label>
        </div>
      )}
    </section>
  )
}

/** 启动门禁：只有文字和图片模型都具备可用连接后才允许进入生成工作流。 */
export default function ModelSetupGate() {
  const [status, setStatus] = useState<InitialModelSetupStatus | null>(null)
  const [providers, setProviders] = useState<Record<Category, SupportedModelProvider[]>>({ text: [], image: [] })
  const [drafts, setDrafts] = useState<Drafts>({ text: defaultDraft('text', []), image: defaultDraft('image', []) })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  /** 同时读取就绪状态和分类供应商清单，避免使用不支持当前类别的服务商。 */
  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [nextStatus, textProviders, imageProviders] = await Promise.all([
        api.initialModelSetup(),
        api.supportedModelProviders('text'),
        api.supportedModelProviders('image'),
      ])
      const nextProviders = { text: textProviders, image: imageProviders }
      setStatus(nextStatus)
      setProviders(nextProviders)
      setDrafts({ text: defaultDraft('text', textProviders), image: defaultDraft('image', imageProviders) })
    } catch (loadError) {
      setError(`无法检查模型配置：${errorMessage(loadError)}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const missing = useMemo(() => ({
    text: !status?.text.ready,
    image: !status?.image.ready,
  }), [status])

  /** 仅提交缺失类别，已经可用的模型保持原样。 */
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!status) return
    const categories: Category[] = ['text', 'image']
    for (const category of categories) {
      if (!missing[category]) continue
      const provider = providers[category].find((item) => item.key === drafts[category].provider_key)
      if (!drafts[category].provider_key || !drafts[category].model_name.trim() || !drafts[category].base_url.trim()) {
        setError(`请完整填写${category === 'text' ? '文字' : '图像'}模型信息`)
        return
      }
      if (provider?.requires_api_key !== false && !drafts[category].api_key.trim()) {
        setError(`请填写${category === 'text' ? '文字' : '图像'}模型的 API Key`)
        return
      }
    }

    setSaving(true)
    setError('')
    try {
      const result = await api.saveInitialModelSetup({
        ...(missing.text ? { text: drafts.text } : {}),
        ...(missing.image ? { image: drafts.image } : {}),
      })
      setStatus(result)
      setDrafts((current) => ({
        text: { ...current.text, api_key: '' },
        image: { ...current.image, api_key: '' },
      }))
    } catch (saveError) {
      setError(errorMessage(saveError))
    } finally {
      setSaving(false)
    }
  }

  if (status?.ready) return null

  if (loading || !status) {
    return (
      <div className="model-setup-mask" role="status" aria-live="polite">
        <div className="model-setup-loading">
          <span className="model-loading-dot" aria-hidden="true" />
          <strong>{loading ? '正在检查模型连接…' : '模型配置检查失败'}</strong>
          {error && <p>{error}</p>}
          {!loading && <button type="button" className="btn primary" onClick={() => void load()}>重新检查</button>}
        </div>
      </div>
    )
  }

  return (
    <div className="model-setup-mask">
      <form className="model-setup-panel" role="dialog" aria-modal="true" aria-labelledby="model-setup-title" onSubmit={submit}>
        <header className="model-setup-head">
          <div>
            <span className="model-setup-kicker">首次配置</span>
            <h1 id="model-setup-title">连接你的生成模型</h1>
            <p>文字和图像是两条独立连接，可以选择不同服务商、模型和 Key。</p>
          </div>
          <div className="model-security-note">
            <span aria-hidden="true">⌁</span>
            <p><strong>Key 只保存在本机</strong><br />保存后界面不会回显</p>
          </div>
        </header>

        <div className="model-setup-grid">
          <ModelConnectionCard
            category="text"
            capability={status.text}
            providers={providers.text}
            draft={drafts.text}
            disabled={saving}
            onChange={(next) => setDrafts((current) => ({ ...current, text: next }))}
          />
          <ModelConnectionCard
            category="image"
            capability={status.image}
            providers={providers.image}
            draft={drafts.image}
            disabled={saving}
            onChange={(next) => setDrafts((current) => ({ ...current, image: next }))}
          />
        </div>

        <footer className="model-setup-foot">
          <div className="model-setup-error" role="alert" aria-live="assertive">{error}</div>
          <button className="btn primary model-save" type="submit" disabled={saving}>
            {saving ? '正在保存…' : '保存并进入工作台'}
          </button>
        </footer>
      </form>
    </div>
  )
}
