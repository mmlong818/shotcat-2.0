import { useNavigate } from 'react-router-dom'
import { PlaceholderTab } from './PlaceholderTab'

export function SettingsTab() {
  const navigate = useNavigate()
  return (
    <PlaceholderTab
      title="项目设置"
      description="项目基础信息、全局风格/种子、协作成员、删除项目等。"
      actionLabel="前往系统设置"
      onAction={() => navigate('/settings')}
    />
  )
}
