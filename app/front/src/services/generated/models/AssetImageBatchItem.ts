/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssetImageReference } from './AssetImageReference';
/**
 * 设定图批量队列项；派生状态在执行时读取已完成的基准图作为参考。
 */
export type AssetImageBatchItem = {
    type: 'character' | 'actor' | 'scene' | 'prop' | 'costume';
    id: string;
    name?: string;
    image_id: number;
    prompt: string;
    reference_type?: ('character' | 'actor' | 'scene' | 'prop' | 'costume' | null);
    reference_entity_id?: (string | null);
    reference_assets?: Array<AssetImageReference>;
};
