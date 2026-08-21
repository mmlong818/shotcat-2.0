/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 一条资产被镜头画面引用的摘要，用于造型页展示。
 */
export type EntityUsageShotRead = {
    /**
     * 镜头 ID
     */
    shot_id: string;
    /**
     * 所属章节 ID
     */
    chapter_id: string;
    /**
     * 章节内镜头序号
     */
    shot_index: number;
    /**
     * 镜头标题
     */
    title: string;
};
