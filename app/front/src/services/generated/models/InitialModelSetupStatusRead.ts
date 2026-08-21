/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelCapabilitySetupRead } from './ModelCapabilitySetupRead';
/**
 * 工作台启动时使用的文字与图片模型配置状态。
 */
export type InitialModelSetupStatusRead = {
    /**
     * 文字与图片模型是否都已就绪
     */
    ready: boolean;
    text: ModelCapabilitySetupRead;
    image: ModelCapabilitySetupRead;
};
