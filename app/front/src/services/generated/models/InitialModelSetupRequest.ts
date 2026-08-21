/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InitialModelConnection } from './InitialModelConnection';
/**
 * 首次启动配置请求；已就绪的类别可以省略并保持原配置。
 */
export type InitialModelSetupRequest = {
    text?: (InitialModelConnection | null);
    image?: (InitialModelConnection | null);
};
