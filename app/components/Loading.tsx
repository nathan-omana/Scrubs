import Icon from "./Icon";

export default function Loading({ title, steps }: { title: string; steps: string[] }) {
  return (
    <section className="panel loading" aria-live="polite">
      <div className="spinner" aria-hidden />
      <h2>{title}</h2>
      <ul>
        {steps.map((s, i) => (
          <li key={s} style={{ animationDelay: `${i * 0.4}s` }}>
            <Icon name="check" size={14} />
            {s}
          </li>
        ))}
      </ul>
    </section>
  );
}
