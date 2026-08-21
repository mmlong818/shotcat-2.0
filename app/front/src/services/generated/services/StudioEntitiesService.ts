/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_dict_str__Any__ } from '../models/ApiResponse_dict_str__Any__';
import type { ApiResponse_EntityDeleteResult_ } from '../models/ApiResponse_EntityDeleteResult_';
import type { ApiResponse_EntityNameExistenceCheckResponse_ } from '../models/ApiResponse_EntityNameExistenceCheckResponse_';
import type { ApiResponse_list_EntityUsageSummaryRead__ } from '../models/ApiResponse_list_EntityUsageSummaryRead__';
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_dict_str__Any___ } from '../models/ApiResponse_PaginatedData_dict_str__Any___';
import type { EntityNameExistenceCheckRequest } from '../models/EntityNameExistenceCheckRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioEntitiesService {
    /**
     * 批量检测资产名称是否存在（模糊匹配，不分页）
     * @returns ApiResponse_EntityNameExistenceCheckResponse_ Successful Response
     * @throws ApiError
     */
    public static checkEntityNamesExistenceApiV1StudioEntitiesExistenceCheckPost({
        requestBody,
    }: {
        requestBody: EntityNameExistenceCheckRequest,
    }): CancelablePromise<ApiResponse_EntityNameExistenceCheckResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/existence-check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一实体列表（分页）
     * @returns ApiResponse_PaginatedData_dict_str__Any___ Successful Response
     * @throws ApiError
     */
    public static listEntitiesApiV1StudioEntitiesEntityTypeGet({
        entityType,
        q,
        style,
        visualStyle,
        projectId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
    }: {
        entityType: string,
        /**
         * 关键字，过滤 name/description
         */
        q?: (string | null),
        /**
         * 题材/风格（单值）
         */
        style?: (string | null),
        /**
         * 画面表现形式（单值：真人/动漫）
         */
        visualStyle?: (string | null),
        /**
         * 按项目过滤（项目级隔离）
         */
        projectId?: (string | null),
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_dict_str__Any___> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}',
            path: {
                'entity_type': entityType,
            },
            query: {
                'q': q,
                'style': style,
                'visual_style': visualStyle,
                'project_id': projectId,
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一创建实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static createEntityApiV1StudioEntitiesEntityTypePost({
        entityType,
        requestBody,
    }: {
        entityType: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}',
            path: {
                'entity_type': entityType,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 造型资产在镜头画面中的使用汇总
     * 供造型页一次加载资产被哪些镜头画面引用。
     * @returns ApiResponse_list_EntityUsageSummaryRead__ Successful Response
     * @throws ApiError
     */
    public static listEntityUsageSummaryApiV1StudioEntitiesEntityTypeUsageSummaryGet({
        entityType,
        projectId,
    }: {
        entityType: string,
        projectId: string,
    }): CancelablePromise<ApiResponse_list_EntityUsageSummaryRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/usage-summary',
            path: {
                'entity_type': entityType,
            },
            query: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一获取实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static getEntityApiV1StudioEntitiesEntityTypeEntityIdGet({
        entityType,
        entityId,
    }: {
        entityType: string,
        entityId: string,
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一更新实体
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static updateEntityApiV1StudioEntitiesEntityTypeEntityIdPatch({
        entityType,
        entityId,
        requestBody,
    }: {
        entityType: string,
        entityId: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一删除实体
     * 删除资产；若为派生状态，则把镜头引用自动回退到基准资产。
     * @returns ApiResponse_EntityDeleteResult_ Successful Response
     * @throws ApiError
     */
    public static deleteEntityApiV1StudioEntitiesEntityTypeEntityIdDelete({
        entityType,
        entityId,
    }: {
        entityType: string,
        entityId: string,
    }): CancelablePromise<ApiResponse_EntityDeleteResult_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一实体图片列表（分页）
     * @returns ApiResponse_PaginatedData_dict_str__Any___ Successful Response
     * @throws ApiError
     */
    public static listEntityImagesApiV1StudioEntitiesEntityTypeEntityIdImagesGet({
        entityType,
        entityId,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
    }: {
        entityType: string,
        entityId: string,
        order?: (string | null),
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_dict_str__Any___> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            query: {
                'order': order,
                'is_desc': isDesc,
                'page': page,
                'page_size': pageSize,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一创建实体图片
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static createEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesPost({
        entityType,
        entityId,
        requestBody,
    }: {
        entityType: string,
        entityId: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一更新实体图片
     * @returns ApiResponse_dict_str__Any__ Successful Response
     * @throws ApiError
     */
    public static updateEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdPatch({
        entityType,
        entityId,
        imageId,
        requestBody,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
        requestBody: Record<string, any>,
    }): CancelablePromise<ApiResponse_dict_str__Any__> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
                'image_id': imageId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 统一删除实体图片
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesImageIdDelete({
        entityType,
        entityId,
        imageId,
    }: {
        entityType: string,
        entityId: string,
        imageId: number,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/entities/{entity_type}/{entity_id}/images/{image_id}',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
                'image_id': imageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
