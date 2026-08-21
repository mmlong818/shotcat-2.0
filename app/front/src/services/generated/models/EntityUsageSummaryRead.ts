/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityUsageShotRead } from './EntityUsageShotRead';
/**
 * 单个资产的镜头使用汇总，未使用时 shots 为空。
 */
export type EntityUsageSummaryRead = {
    /**
     * 资产 ID
     */
    entity_id: string;
    /**
     * 引用该资产的镜头
     */
    shots?: Array<EntityUsageShotRead>;
};
