/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FrameImageBatchItem } from './FrameImageBatchItem';
export type FrameImageBatchRequest = {
    items?: Array<FrameImageBatchItem>;
    model_id?: (string | null);
    target_ratio?: '16:9' | '4:3' | '1:1' | '3:4' | '9:16' | '21:9' | '3:2' | '2:3';
    resolution_profile?: ('standard' | 'high' | null);
};
