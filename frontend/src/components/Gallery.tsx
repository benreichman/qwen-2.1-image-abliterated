import type { ImageRecord } from '../api'

interface Props {
  items: ImageRecord[]
  selectedId: string | null
  onSelect: (img: ImageRecord) => void
}

export function Gallery({ items, selectedId, onSelect }: Props) {
  if (items.length === 0) return null
  return (
    <section className="gallery" aria-label="History">
      {items.map((img) => (
        <button
          key={img.id}
          type="button"
          className={img.id === selectedId ? 'thumb on' : 'thumb'}
          onClick={() => onSelect(img)}
          title={String(img.params.prompt ?? '')}
        >
          <img src={img.url} alt="" loading="lazy" />
        </button>
      ))}
    </section>
  )
}
