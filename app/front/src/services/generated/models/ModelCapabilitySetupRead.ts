/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelCategoryKey } from './ModelCategoryKey';
/**
 * 单类模型的启动可用状态；只返回是否存在 Key，不返回 Key 本身。
 */
export type ModelCapabilitySetupRead = {
    /**
     * 模型类别
     */
    category: ModelCategoryKey;
    /**
     * 该类别是否已具备可用模型和供应商
     */
    ready: boolean;
    /**
     * 未就绪原因代码
     */
    reason?: (string | null);
    /**
     * 面向用户的状态说明
     */
    message: string;
    /**
     * 当前默认模型 ID
     */
    model_id?: (string | null);
    /**
     * 当前默认模型名称
     */
    model_name?: (string | null);
    /**
     * 当前供应商 ID
     */
    provider_id?: (string | null);
    /**
     * 当前供应商稳定键
     */
    provider_key?: (string | null);
    /**
     * 当前供应商名称
     */
    provider_name?: (string | null);
    /**
     * 供应商是否已保存 API Key
     */
    has_api_key?: boolean;
};
