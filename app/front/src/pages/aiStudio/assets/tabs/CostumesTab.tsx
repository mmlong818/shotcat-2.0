import { AssetTypeTab } from './AssetTypeTab'
import { useNavigate } from 'react-router-dom'
import { StudioEntitiesApi, toStudioEntityRecord } from '../../../../services/studioEntities'

export function CostumesTab() {
  const navigate = useNavigate()

  return (
    <AssetTypeTab
      label="服装"
      tabKey="costume"
      listAssets={async ({ q, page, pageSize }) => {
        const res = await StudioEntitiesApi.list('costume', { q: q ?? null, page, pageSize })
        const items = (res.data?.items ?? [])
          .map(toStudioEntityRecord)
          .filter((item): item is NonNullable<typeof item> => item !== null)
        return { items, total: res.data?.pagination.total ?? 0 }
      }}
      createAsset={async (payload) => {
        const res = await StudioEntitiesApi.create('costume', payload as Record<string, unknown>)
        if (!res.data) throw new Error('empty costume')
        const asset = toStudioEntityRecord(res.data)
        if (!asset) throw new Error('invalid costume response')
        return asset
      }}
      updateAsset={async (id, payload) => {
        const res = await StudioEntitiesApi.update('costume', id, payload as Record<string, unknown>)
        if (!res.data) throw new Error('empty costume')
        const asset = toStudioEntityRecord(res.data)
        if (!asset) throw new Error('invalid costume response')
        return asset
      }}
      deleteAsset={async (id) => {
        await StudioEntitiesApi.remove('costume', id)
      }}
      onEditAsset={(asset) => {
        navigate(`/assets/costumes/${asset.id}/edit`)
      }}
    />
  )
}
