/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 批量生成时动态读取的实体参考图，用于照片/屏幕等强关联道具。
 */
export type AssetImageReference = {
    type: 'character' | 'actor' | 'scene' | 'prop' | 'costume';
    entity_id: string;
};
