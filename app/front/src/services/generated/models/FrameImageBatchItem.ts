/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShotFrameType } from './ShotFrameType';
import type { ShotLinkedAssetItem } from './ShotLinkedAssetItem';
export type FrameImageBatchItem = {
    shot_id: string;
    name?: string;
    /**
     * first | key | last
     */
    frame_type?: ShotFrameType;
    images?: Array<ShotLinkedAssetItem>;
};
