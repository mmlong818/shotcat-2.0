import React, { useEffect, useState } from 'react'
import { Card, Layout, Button, message } from 'antd'
import {
  ScissorOutlined,
  PlusOutlined,
  ExportOutlined,
  PlayCircleOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons'
import { useParams, Link } from 'react-router-dom'
import api from '../../../services/aiStudioApi'
import type { TimelineClip } from '../../../mocks/data'

const { Content } = Layout

const VideoEditor: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const [clips, setClips] = useState<TimelineClip[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const list = await api.timeline.get(projectId)
      setClips(Array.isArray(list) ? list : [])
    } catch {
      message.error('加载时间线失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [projectId])

  return (
    <div className="space-y-4">
      <div className="mb-2">
        <Link
          to={projectId ? `/projects/${projectId}/chapters` : '/projects'}
          className="text-sm text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> {projectId ? '返回章节列表' : '项目列表'}
        </Link>
      </div>
      <Card
        title="视频编辑"
        extra={
          <Button type="primary" icon={<ExportOutlined />}>
            导出成片
          </Button>
        }
      >
        <div className="flex items-center gap-2 mb-4">
          <Button icon={<ScissorOutlined />}>剪切</Button>
          <Button icon={<PlusOutlined />}>添加效果</Button>
          <Button icon={<PlayCircleOutlined />}>预览</Button>
        </div>

        <Layout className="bg-gray-50 rounded p-4 min-h-[400px]">
          <div className="mb-4">
            <div className="text-sm text-gray-500 mb-2">素材库</div>
            <div className="flex gap-2 flex-wrap">
              {clips.map((c) => (
                <div
                  key={c.id}
                  className="px-3 py-2 bg-white rounded border border-gray-200 text-sm cursor-pointer hover:border-blue-400"
                >
                  {c.label}
                </div>
              ))}
              {clips.length === 0 && !loading && (
                <span className="text-gray-500">暂无素材，可从文件管理导入</span>
              )}
            </div>
          </div>
          <Content>
            <div className="text-sm text-gray-500 mb-2">时间线（拖拽素材到轨道）</div>
            <div className="bg-white rounded border border-gray-200 overflow-hidden">
              <div className="grid grid-cols-[80px_1fr] border-b border-gray-200">
                <div className="px-2 py-2 bg-gray-50 text-gray-600 text-xs font-medium">轨道</div>
                <div className="px-2 py-2 bg-gray-50 text-gray-600 text-xs font-medium">内容</div>
              </div>
              <div className="grid grid-cols-[80px_1fr] border-b border-gray-100">
                <div className="px-2 py-3 bg-gray-50/80 text-gray-500 text-xs">视频轨道</div>
                <div className="px-2 py-3 min-h-[56px] flex items-center gap-2 flex-wrap">
                  {clips.filter((c) => c.type === 'video').map((c) => (
                    <div
                      key={c.id}
                      className="px-2 py-1.5 bg-blue-50 border border-blue-200 rounded text-sm cursor-move"
                    >
                      {c.label}（{c.start}s–{c.end}s）
                    </div>
                  ))}
                  {clips.filter((c) => c.type === 'video').length === 0 && (
                    <span className="text-gray-400 text-xs">拖入视频素材</span>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-[80px_1fr]">
                <div className="px-2 py-3 bg-gray-50/80 text-gray-500 text-xs">音频轨道</div>
                <div className="px-2 py-3 min-h-[56px] flex items-center gap-2 flex-wrap">
                  {clips.filter((c) => c.type === 'audio').map((c) => (
                    <div
                      key={c.id}
                      className="px-2 py-1.5 bg-green-50 border border-green-200 rounded text-sm cursor-move"
                    >
                      {c.label}（{c.start}s–{c.end}s）
                    </div>
                  ))}
                  {clips.filter((c) => c.type === 'audio').length === 0 && (
                    <span className="text-gray-400 text-xs">拖入音频/配乐</span>
                  )}
                </div>
              </div>
            </div>
          </Content>
        </Layout>
      </Card>
    </div>
  )
}

export default VideoEditor
