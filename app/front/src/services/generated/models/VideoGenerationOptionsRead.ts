/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 当前默认视频模型对应的生成参数选项。
 */
export type VideoGenerationOptionsRead = {
    /**
     * 供应商稳定键
     */
    provider: string;
    /**
     * 默认视频模型 ID
     */
    model_id: string;
    /**
     * 默认视频模型名称
     */
    model_name: string;
    /**
     * 当前模型允许的比例选项
     */
    allowed_ratios?: Array<string>;
    /**
     * 当前模型默认比例
     */
    default_ratio: string;
};

