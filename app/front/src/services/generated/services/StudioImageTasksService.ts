/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_AssetImageBatchCreated_ } from '../models/ApiResponse_AssetImageBatchCreated_';
import type { ApiResponse_AssetImageBatchStatus_ } from '../models/ApiResponse_AssetImageBatchStatus_';
import type { ApiResponse_FrameImageBatchCreated_ } from '../models/ApiResponse_FrameImageBatchCreated_';
import type { ApiResponse_FrameImageBatchStatus_ } from '../models/ApiResponse_FrameImageBatchStatus_';
import type { ApiResponse_RenderedPromptResponse_ } from '../models/ApiResponse_RenderedPromptResponse_';
import type { ApiResponse_RenderedShotFramePromptRead_ } from '../models/ApiResponse_RenderedShotFramePromptRead_';
import type { ApiResponse_TaskCreated_ } from '../models/ApiResponse_TaskCreated_';
import type { AssetImageBatchRequest } from '../models/AssetImageBatchRequest';
import type { FrameImageBatchRequest } from '../models/FrameImageBatchRequest';
import type { ShotFrameImageTaskRequest } from '../models/ShotFrameImageTaskRequest';
import type { ShotFramePromptRenderRequest } from '../models/ShotFramePromptRenderRequest';
import type { StudioImageTaskRequest } from '../models/StudioImageTaskRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioImageTasksService {
    /**
     * 批量排队生成设定页造型图
     * @returns ApiResponse_AssetImageBatchCreated_ Successful Response
     * @throws ApiError
     */
    public static createAssetImageBatchApiV1StudioImageTasksAssetBatchesPost({
        requestBody,
    }: {
        requestBody: AssetImageBatchRequest,
    }): CancelablePromise<ApiResponse_AssetImageBatchCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/asset-batches',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询设定页造型图批量生成进度
     * @returns ApiResponse_AssetImageBatchStatus_ Successful Response
     * @throws ApiError
     */
    public static getAssetImageBatchApiV1StudioImageTasksAssetBatchesBatchIdGet({
        batchId,
    }: {
        batchId: string,
    }): CancelablePromise<ApiResponse_AssetImageBatchStatus_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/image-tasks/asset-batches/{batch_id}',
            path: {
                'batch_id': batchId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 停止设定页造型图批量生成
     * @returns ApiResponse_AssetImageBatchStatus_ Successful Response
     * @throws ApiError
     */
    public static cancelAssetImageBatchApiV1StudioImageTasksAssetBatchesBatchIdCancelPost({
        batchId,
    }: {
        batchId: string,
    }): CancelablePromise<ApiResponse_AssetImageBatchStatus_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/asset-batches/{batch_id}/cancel',
            path: {
                'batch_id': batchId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量排队生成镜头缺失画面
     * @returns ApiResponse_FrameImageBatchCreated_ Successful Response
     * @throws ApiError
     */
    public static createFrameImageBatchApiV1StudioImageTasksFrameBatchesPost({
        requestBody,
    }: {
        requestBody: FrameImageBatchRequest,
    }): CancelablePromise<ApiResponse_FrameImageBatchCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/frame-batches',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询镜头画面批量生成进度
     * @returns ApiResponse_FrameImageBatchStatus_ Successful Response
     * @throws ApiError
     */
    public static getFrameImageBatchApiV1StudioImageTasksFrameBatchesBatchIdGet({
        batchId,
    }: {
        batchId: string,
    }): CancelablePromise<ApiResponse_FrameImageBatchStatus_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/image-tasks/frame-batches/{batch_id}',
            path: {
                'batch_id': batchId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 停止镜头画面批量生成
     * @returns ApiResponse_FrameImageBatchStatus_ Successful Response
     * @throws ApiError
     */
    public static cancelFrameImageBatchApiV1StudioImageTasksFrameBatchesBatchIdCancelPost({
        batchId,
    }: {
        batchId: string,
    }): CancelablePromise<ApiResponse_FrameImageBatchStatus_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/frame-batches/{batch_id}/cancel',
            path: {
                'batch_id': batchId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 演员图片生成（任务版）
     * 为指定演员创建图片生成任务，并通过 `GenerationTaskLink` 关联。
     * @returns ApiResponse_TaskCreated_ Successful Response
     * @throws ApiError
     */
    public static createActorImageGenerationTaskApiV1StudioImageTasksActorsActorIdImageTasksPost({
        actorId,
        requestBody,
    }: {
        actorId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_TaskCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/actors/{actor_id}/image-tasks',
            path: {
                'actor_id': actorId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 演员图片提示词渲染
     * @returns ApiResponse_RenderedPromptResponse_ Successful Response
     * @throws ApiError
     */
    public static renderActorImagePromptApiV1StudioImageTasksActorsActorIdRenderPromptPost({
        actorId,
        requestBody,
    }: {
        actorId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_RenderedPromptResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/actors/{actor_id}/render-prompt',
            path: {
                'actor_id': actorId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 道具/场景/服装图片生成（任务版）
     * 为道具/场景/服装创建图片生成任务。
     *
     * - asset_type: prop / scene / costume
     * - path 参数 asset_id 为对应资产 ID
     * - body.image_id 必须为该资产下对应图片表记录的 ID（PropImage/SceneImage/CostumeImage）
     * @returns ApiResponse_TaskCreated_ Successful Response
     * @throws ApiError
     */
    public static createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
        assetType,
        assetId,
        requestBody,
    }: {
        assetType: string,
        assetId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_TaskCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/assets/{asset_type}/{asset_id}/image-tasks',
            path: {
                'asset_type': assetType,
                'asset_id': assetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 道具/场景/服装图片提示词渲染
     * @returns ApiResponse_RenderedPromptResponse_ Successful Response
     * @throws ApiError
     */
    public static renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
        assetType,
        assetId,
        requestBody,
    }: {
        assetType: string,
        assetId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_RenderedPromptResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/assets/{asset_type}/{asset_id}/render-prompt',
            path: {
                'asset_type': assetType,
                'asset_id': assetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 角色图片生成（任务版）
     * 为角色创建图片生成任务（对应 CharacterImage 业务）。
     *
     * - path 参数 character_id 为 Character.id
     * - body.image_id 必须为该角色下的 CharacterImage.id
     * @returns ApiResponse_TaskCreated_ Successful Response
     * @throws ApiError
     */
    public static createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
        characterId,
        requestBody,
    }: {
        characterId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_TaskCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/characters/{character_id}/image-tasks',
            path: {
                'character_id': characterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 角色图片提示词渲染
     * @returns ApiResponse_RenderedPromptResponse_ Successful Response
     * @throws ApiError
     */
    public static renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
        characterId,
        requestBody,
    }: {
        characterId: string,
        requestBody: StudioImageTaskRequest,
    }): CancelablePromise<ApiResponse_RenderedPromptResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/characters/{character_id}/render-prompt',
            path: {
                'character_id': characterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 镜头分镜帧图片生成（任务版）
     * 为镜头分镜帧图片生成任务（基于 `shot_id + frame_type` 自动定位数据）。
     * @returns ApiResponse_TaskCreated_ Successful Response
     * @throws ApiError
     */
    public static createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: ShotFrameImageTaskRequest,
    }): CancelablePromise<ApiResponse_TaskCreated_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/shot/{shot_id}/frame-image-tasks',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 镜头分镜帧提示词渲染
     * @returns ApiResponse_RenderedShotFramePromptRead_ Successful Response
     * @throws ApiError
     */
    public static renderShotFramePromptApiV1StudioImageTasksShotShotIdFrameRenderPromptPost({
        shotId,
        requestBody,
    }: {
        shotId: string,
        requestBody: ShotFramePromptRenderRequest,
    }): CancelablePromise<ApiResponse_RenderedShotFramePromptRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/image-tasks/shot/{shot_id}/frame-render-prompt',
            path: {
                'shot_id': shotId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
