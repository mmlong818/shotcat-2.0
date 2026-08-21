/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 首次启动时保存的一类外部模型连接。
 */
export type InitialModelConnection = {
    /**
     * 供应商稳定键
     */
    provider_key: string;
    /**
     * 兼容 API Base URL
     */
    base_url?: (string | null);
    /**
     * API Key（敏感，不在响应中回显）
     */
    api_key?: string;
    /**
     * 供应商侧模型 ID
     */
    model_name: string;
};
