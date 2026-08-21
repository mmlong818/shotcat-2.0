/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type RenderedPromptResponse = {
    /**
     * 渲染后的提示词（已套用模板与变量替换）
     */
    prompt: string;
    /**
     * 参考图 file_id 列表（自动选择；顺序有效）
     */
    images?: Array<string>;
};

