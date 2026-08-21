/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FrameImageBatchStatus = {
    batch_id: string;
    status: string;
    total: number;
    queued: number;
    running: number;
    succeeded: number;
    failed: number;
    cancelled: number;
    current?: string;
    current_task_id?: (string | null);
    error?: string;
    items?: Array<Record<string, any>>;
};
