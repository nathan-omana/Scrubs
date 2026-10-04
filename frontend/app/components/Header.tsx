export default function Header() {
  return (
    <header className="scrubs-header">
      <div className="grid-container scrubs-header__inner">
        <div className="scrubs-brand">
          <span className="scrubs-brand__mark" aria-hidden>
            S
          </span>
          <div>
            <div className="scrubs-brand__name">Scrubs</div>
            <div className="scrubs-brand__tagline">Clinical document de-identification</div>
          </div>
        </div>
        <nav className="scrubs-header__links" aria-label="Utility">
          <a href="#">How it works</a>
          <a href="#">Audit log</a>
          <span className="scrubs-header__user">Signed in: Clinician</span>
        </nav>
      </div>
    </header>
  );
}
