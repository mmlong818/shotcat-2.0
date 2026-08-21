import { StudioImageTasksService, type StudioImageTaskRequest } from '../../../services/generated'
import { StudioEntitiesApi, type StudioEntityType } from '../../../services/studioEntities'
import type { AssetEditPageBaseProps, BaseAsset, BaseAssetImage } from './components/AssetEditPageBase'

type AdapterConfig = Omit<
  AssetEditPageBaseProps<BaseAsset, BaseAssetImage>,
  'assetId' | 'onNavigate'
>

type UpdateImagePayload = {
  file_id: string
  width?: number | null
  height?: number | null
  format?: string | null
}

function normalizeUpdateImagePayload(payload: UpdateImagePayload): UpdateImagePayload {
  return {
    ...payload,
    format: payload.format ?? 'png',
  }
}

const VALID_VIEW_ANGLES = new Set(['FRONT', 'LEFT', 'RIGHT', 'BACK', 'THREE_QUARTER', 'TOP', 'DETAIL'])

function isAssetViewAngle(value: unknown): value is NonNullable<BaseAssetImage['view_angle']> {
  return typeof value === 'string' && VALID_VIEW_ANGLES.has(value)
}

function toBaseAsset(value: unknown): BaseAsset | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string') return null
  const tags = Array.isArray(value.tags) && value.tags.every((tag) => typeof tag === 'string') ? value.tags : undefined
  const visualStyle = value.visual_style === '现实' || value.visual_style === '动漫' ? value.visual_style : undefined
  return {
    id: value.id,
    name: value.name,
    description: typeof value.description === 'string' ? value.description : undefined,
    tags,
    view_count: typeof value.view_count === 'number' && Number.isFinite(value.view_count) ? value.view_count : undefined,
    visual_style: visualStyle,
    style: typeof value.style === 'string' ? value.style : undefined,
  }
}

function toBaseAssetImage(value: unknown): BaseAssetImage | null {
  if (!isRecord(value) || typeof value.id !== 'number' || !Number.isInteger(value.id)) return null
  return {
    id: value.id,
    view_angle: isAssetViewAngle(value.view_angle) ? value.view_angle : undefined,
    file_id: typeof value.file_id === 'string' || value.file_id === null ? value.file_id : undefined,
    width: typeof value.width === 'number' && Number.isFinite(value.width) ? value.width : undefined,
    height: typeof value.height === 'number' && Number.isFinite(value.height) ? value.height : undefined,
    format: typeof value.format === 'string' ? value.format : undefined,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function taskRequest(imageId: number, payload?: { prompt: string; images: string[] }): StudioImageTaskRequest {
  return {
    image_id: imageId,
    model_id: null,
    ...(payload ? { prompt: payload.prompt, images: payload.images } : {}),
  }
}

async function renderPrompt(entityType: StudioEntityType, id: string, imageId: number): Promise<{ prompt: string; images: string[] }> {
  const response = entityType === 'character'
    ? await StudioImageTasksService.renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
        characterId: id,
        requestBody: taskRequest(imageId),
      })
    : entityType === 'actor'
      ? await StudioImageTasksService.renderActorImagePromptApiV1StudioImageTasksActorsActorIdRenderPromptPost({
          actorId: id,
          requestBody: taskRequest(imageId),
        })
      : await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
          assetType: entityType,
          assetId: id,
          requestBody: taskRequest(imageId),
        })
  return { prompt: response.data?.prompt ?? '', images: response.data?.images ?? [] }
}

async function createGenerationTask(entityType: StudioEntityType, id: string, imageId: number, payload: { prompt: string; images: string[] }): Promise<string | null> {
  const response = entityType === 'character'
    ? await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
        characterId: id,
        requestBody: taskRequest(imageId, payload),
      })
    : entityType === 'actor'
      ? await StudioImageTasksService.createActorImageGenerationTaskApiV1StudioImageTasksActorsActorIdImageTasksPost({
          actorId: id,
          requestBody: taskRequest(imageId, payload),
        })
      : await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
          assetType: entityType,
          assetId: id,
          requestBody: taskRequest(imageId, payload),
        })
  return response.data?.task_id ?? null
}

function createAdapter(config: Pick<AdapterConfig, 'missingAssetIdText' | 'assetDisplayName' | 'backTo' | 'relationType'> & { entityType: StudioEntityType }): AdapterConfig {
  const { entityType, ...adapter } = config
  return {
    ...adapter,
    getAsset: async (id) => toBaseAsset((await StudioEntitiesApi.get(entityType, id)).data),
    updateAsset: async (id, payload) => toBaseAsset((await StudioEntitiesApi.update(entityType, id, payload as Record<string, unknown>)).data),
    listImages: async (id) => {
      const items = (await StudioEntitiesApi.listImages(entityType, id, { page: 1, pageSize: 100 })).data?.items ?? []
      return items.map(toBaseAssetImage).filter((image): image is BaseAssetImage => image !== null)
    },
    createImageSlot: async (id, angle) => {
      await StudioEntitiesApi.createImage(entityType, id, { view_angle: angle })
    },
    updateImage: async (id, imageId, payload) => {
      await StudioEntitiesApi.updateImage(entityType, id, imageId, normalizeUpdateImagePayload(payload))
    },
    renderPrompt: (id, imageId) => renderPrompt(entityType, id, imageId),
    createGenerationTask: (id, imageId, payload) => createGenerationTask(entityType, id, imageId, payload),
  }
}

export const assetAdapters = {
  character: createAdapter({
    entityType: 'character',
    missingAssetIdText: '缺少 character_id',
    assetDisplayName: '角色',
    backTo: '/projects',
    relationType: 'character_image',
  }),
  actor: createAdapter({
    entityType: 'actor',
    missingAssetIdText: '缺少 actor_id',
    assetDisplayName: '演员',
    backTo: '/assets?tab=actor',
    relationType: 'actor_image',
  }),
  scene: createAdapter({
    entityType: 'scene',
    missingAssetIdText: '缺少 scene_id',
    assetDisplayName: '场景',
    backTo: '/assets?tab=scene',
    relationType: 'scene_image',
  }),
  prop: createAdapter({
    entityType: 'prop',
    missingAssetIdText: '缺少 prop_id',
    assetDisplayName: '道具',
    backTo: '/assets?tab=prop',
    relationType: 'prop_image',
  }),
  costume: createAdapter({
    entityType: 'costume',
    missingAssetIdText: '缺少 costume_id',
    assetDisplayName: '服装',
    backTo: '/assets?tab=costume',
    relationType: 'costume_image',
  }),
}
