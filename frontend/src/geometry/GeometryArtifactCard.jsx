function TextList({ title, items, renderItem }) {
  if (!items?.length) return null
  return (
    <section className="geometry-card-section">
      <h4>{title}</h4>
      <ul>{items.map((item, index) => <li key={item.id ?? index}>{renderItem(item)}</li>)}</ul>
    </section>
  )
}

export default function GeometryArtifactCard({ artifact, onOpen }) {
  return (
    <article className="geometry-card" data-testid="geometry-artifact">
      <div className="geometry-card-heading">
        <div>
          <span className="geometry-kind">Hình dựng tương tác · {artifact.app === '3d' ? '3D' : '2D'}</span>
          <h3>{artifact.title}</h3>
        </div>
        <button type="button" className="geometry-open-btn" onClick={() => onOpen(artifact)}>
          Mở hình
        </button>
      </div>

      <TextList title="Giả thiết" items={artifact.givens} renderItem={item => (
        <>
          <span>{item.text}</span>
          {item.source_text && <small>Nguồn: {item.source_text}</small>}
        </>
      )} />
      <TextList title="Mục tiêu" items={artifact.goals} renderItem={item => <span>{item.text ?? item}</span>} />
      <TextList title="Lựa chọn minh hoạ" items={artifact.display_choices} renderItem={item => <span>{item.text ?? item}</span>} />

      <p className="geometry-summary">{artifact.steps?.length ?? 0} bước dựng. Hình dùng để minh hoạ và khám phá; không thay cho chứng minh.</p>
    </article>
  )
}
