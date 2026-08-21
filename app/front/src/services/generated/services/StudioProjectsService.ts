/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiResponse_NoneType_ } from '../models/ApiResponse_NoneType_';
import type { ApiResponse_PaginatedData_ProjectRead__ } from '../models/ApiResponse_PaginatedData_ProjectRead__';
import type { ApiResponse_ProjectRead_ } from '../models/ApiResponse_ProjectRead_';
import type { ApiResponse_ProjectStyleOptionsRead_ } from '../models/ApiResponse_ProjectStyleOptionsRead_';
import type { ProjectCreate } from '../models/ProjectCreate';
import type { ProjectUpdate } from '../models/ProjectUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class StudioProjectsService {
    /**
     * 获取项目风格候选项
     * @returns ApiResponse_ProjectStyleOptionsRead_ Successful Response
     * @throws ApiError
     */
    public static getProjectStyleOptionsApiV1StudioProjectsStyleOptionsGet(): CancelablePromise<ApiResponse_ProjectStyleOptionsRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/projects/style-options',
        });
    }
    /**
     * 项目列表（分页）
     * @returns ApiResponse_PaginatedData_ProjectRead__ Successful Response
     * @throws ApiError
     */
    public static listProjectsApiV1StudioProjectsGet({
        q,
        order,
        isDesc = false,
        page = 1,
        pageSize = 10,
    }: {
        /**
         * 关键字，过滤 name/description
         */
        q?: (string | null),
        /**
         * 排序字段
         */
        order?: (string | null),
        /**
         * 是否倒序
         */
        isDesc?: boolean,
        page?: number,
        pageSize?: number,
    }): CancelablePromise<ApiResponse_PaginatedData_ProjectRead__> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/projects',
            query: {
                'q': q,
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
     * 创建项目
     * @returns ApiResponse_ProjectRead_ Successful Response
     * @throws ApiError
     */
    public static createProjectApiV1StudioProjectsPost({
        requestBody,
    }: {
        requestBody: ProjectCreate,
    }): CancelablePromise<ApiResponse_ProjectRead_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/studio/projects',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量导出项目关键帧 ZIP
     * 导出已有关键帧，ZIP 内按章节、镜头序号和镜头标题命名。
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportProjectKeyframesApiV1StudioProjectsProjectIdKeyframesExportGet({
        projectId,
    }: {
        projectId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/projects/{project_id}/keyframes/export',
            path: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量导出项目设定图 ZIP
     * 导出角色、场景、道具的全部已生成设定图，按类型目录和资产名称命名。
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportProjectAssetsApiV1StudioProjectsProjectIdAssetsExportGet({
        projectId,
    }: {
        projectId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/projects/{project_id}/assets/export',
            path: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取项目
     * @returns ApiResponse_ProjectRead_ Successful Response
     * @throws ApiError
     */
    public static getProjectApiV1StudioProjectsProjectIdGet({
        projectId,
    }: {
        projectId: string,
    }): CancelablePromise<ApiResponse_ProjectRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/studio/projects/{project_id}',
            path: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新项目
     * @returns ApiResponse_ProjectRead_ Successful Response
     * @throws ApiError
     */
    public static updateProjectApiV1StudioProjectsProjectIdPatch({
        projectId,
        requestBody,
    }: {
        projectId: string,
        requestBody: ProjectUpdate,
    }): CancelablePromise<ApiResponse_ProjectRead_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/studio/projects/{project_id}',
            path: {
                'project_id': projectId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除项目
     * @returns ApiResponse_NoneType_ Successful Response
     * @throws ApiError
     */
    public static deleteProjectApiV1StudioProjectsProjectIdDelete({
        projectId,
    }: {
        projectId: string,
    }): CancelablePromise<ApiResponse_NoneType_> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/studio/projects/{project_id}',
            path: {
                'project_id': projectId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
