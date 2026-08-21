/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 删除资产后的引用回退结果。
 */
export type EntityDeleteResult = {
    /**
     * 已删除的资产 ID
     */
    deleted_entity_id: string;
    /**
     * 派生状态回退到的基准资产 ID
     */
    fallback_entity_id?: (string | null);
    /**
     * 派生状态回退到的基准资产名称
     */
    fallback_entity_name?: (string | null);
    /**
     * 已改为引用基准资产的镜头数量
     */
    reassigned_shot_count?: number;
};
