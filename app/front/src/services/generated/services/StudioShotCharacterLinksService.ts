/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_list_ShotCharacterLinkRead__ } from '../models/ApiResponse_list_ShotCharacterLinkRead__';
import type { ApiResponse_ShotCharacterLinkRead_ } from '../models/ApiResponse_ShotCharacterLinkRead_';
import type { ShotCharacterLinkCreate } from '../models/ShotCharacterLinkCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioShotCharacterLinksService {
    /**
     * 查询镜头角色关联列表（ShotCharacterLink）
     * @returns ApiResponse_list_ShotCharacterLinkRead__ Successful Response
     * @throws ApiError
     */
    public static listShotCharacterLinksApiV1StudioShotCharacterLinksGet({
        shotId,
        chapterId,
    }: {
        /**
         * 镜头 ID（与 chapter_id 二选一）
         */
        shotId?: (string | null),
        /**
         * 章节 ID（批量查询整章镜头的角色关联）
         */
        chapterId?: (string | null),
    }): CancelablePromise<ApiResponse_list_ShotCharacterLinkRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/shot-character-links',
            query: {
                'shot_id': shotId,
                'chapter_id': chapterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建/更新镜头角色关联（ShotCharacterLink）
     * @returns ApiResponse_ShotCharacterLinkRead_ Successful Response
     * @throws ApiError
     */
    public static upsertShotCharacterLinkApiV1StudioShotCharacterLinksPost({
        requestBody,
    }: {
        requestBody: ShotCharacterLinkCreate,
    }): CancelablePromise<ApiResponse_ShotCharacterLinkRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/shot-character-links',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
