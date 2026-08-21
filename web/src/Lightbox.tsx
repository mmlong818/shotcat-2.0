// 点击图片放大看全图：全屏灯箱，点任意处关闭
export default function Lightbox({ url, onClose }: { url: string | null; onClose: () => void }) {
  if (!url) return null
  return (
    <div className="lightbox" onClick={onClose}>
      <span className="lb-close" onClick={onClose}>✕</span>
      <img src={url} alt="" onClick={(e) => e.stopPropagation()} />
    </div>
  )
}
