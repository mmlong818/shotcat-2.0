import { StudioEntitiesService } from './generated'

export type StudioEntityType = 'actor' | 'character' | 'scene' | 'prop' | 'costume'

export type StudioEntityRecord = {
  id: string
  name: string
  description?: string | null
  tags?: string[]
  view_count?: number
  visual_style?: string
  style?: string
  thumbnail?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function optionalStringOrNull(value: unknown): string | null | undefined {
  return value === null || typeof value === 'string' ? value : undefined
}

function optionalFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function toStudioEntityRecord(value: unknown): StudioEntityRecord | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string') {
    return null
  }

  const tags = Array.isArray(value.tags) && value.tags.every((tag) => typeof tag === 'string') ? value.tags : undefined
  return {
    id: value.id,
    name: value.name,
    description: optionalStringOrNull(value.description),
    tags,
    view_count: optionalFiniteNumber(value.view_count),
    visual_style: optionalString(value.visual_style),
    style: optionalString(value.style),
    thumbnail: optionalString(value.thumbnail),
  }
}

export const StudioEntitiesApi = {
  list(entityType: StudioEntityType, params: { q?: string | null; page?: number; pageSize?: number; order?: string | null; isDesc?: boolean }) {
    return StudioEntitiesService.listEntitiesApiV1StudioEntitiesEntityTypeGet({
      entityType,
      q: params.q ?? null,
      page: params.page ?? 1,
      pageSize: params.pageSize ?? 10,
      order: params.order ?? null,
      isDesc: params.isDesc ?? false,
    })
  },
  get(entityType: StudioEntityType, entityId: string) {
    return StudioEntitiesService.getEntityApiV1StudioEntitiesEntityTypeEntityIdGet({
      entityType,
      entityId,
    })
  },
  create(entityType: StudioEntityType, payload: Record<string, unknown>) {
    return StudioEntitiesService.createEntityApiV1StudioEntitiesEntityTypePost({
      entityType,
      requestBody: payload,
    })
  },
  update(entityType: StudioEntityType, entityId: string, payload: Record<string, unknown>) {
    return StudioEntitiesService.updateEntityApiV1StudioEntitiesEntityTypeEntityIdPatch({
      entityType,
      entityId,
      requestBody: payload,
    })
  },
  remove(entityType: StudioEntityType, entityId: string) {
    return StudioEntitiesService.deleteEntityApiV1StudioEntitiesEntityTypeEntityIdDelete({
      entityType,
      entityId,
    })
  },
  listImages(entityType: StudioEntityType, entityId: string, params: { page?: number; pageSize?: number; order?: string | null; isDesc?: boolean }) {
    return StudioEntitiesService.listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
      entityType,
      entityId,
      page: params.page ?? 1,
      pageSize: params.pageSize ?? 10,
      order: params.order ?? null,
      isDesc: params.isDesc ?? false,
    })
  },
  createImage(entityType: StudioEntityType, entityId: string, payload: Record<string, unknown>) {
    return StudioEntitiesService.createEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesPost({
      entityType,
      entityId,
      requestBody: payload,
    })
  },
  updateImage(entityType: StudioEntityType, entityId: string, imageId: number, payload: Record<string, unknown>) {
    return StudioEntitiesService.updateEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdPatch({
      entityType,
      entityId,
      imageId,
      requestBody: payload,
    })
  },
  deleteImage(entityType: StudioEntityType, entityId: string, imageId: number) {
    return StudioEntitiesService.deleteEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdDelete({
      entityType,
      entityId,
      imageId,
    })
  },
}

