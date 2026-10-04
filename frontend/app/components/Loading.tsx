export default function Loading({ messages }: { messages: string[] }) {
  return (
    <section className="scrubs-panel scrubs-loading" aria-live="polite">
      <div className="scrubs-spinner" aria-hidden />
      <h2 className="margin-top-2 margin-bottom-1">Processing</h2>
      <ul className="scrubs-loading__list">
        {messages.map((m, i) => (
          <li key={m} style={{ animationDelay: `${i * 0.5}s` }}>
            {m}
          </li>
        ))}
      </ul>
    </section>
  );
}
