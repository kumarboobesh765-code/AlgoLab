export default function PartnershipPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-14">
      <h1 className="text-3xl font-bold text-slate-900">Partnership</h1>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">
        We work with brokers, prop desks, educator-creators, and SEBI-registered RIAs who want to
        distribute or white-label the StrategyLab product suite.
      </p>

      <h2 className="mt-8 text-lg font-semibold text-slate-900">Who we partner with</h2>
      <ul className="mt-3 space-y-2 text-sm text-slate-700">
        <li>
          <strong>Brokers</strong> — co-marketing, deeper OMS integrations, volume rebates.
        </li>
        <li>
          <strong>Educators</strong> — embed a private-branded Leg Builder into your course or
          YouTube channel; revenue share on referred sign-ups.
        </li>
        <li>
          <strong>SEBI RIAs</strong> — client portfolios under your custody, full audit trail.
        </li>
        <li>
          <strong>Prop desks</strong> — risk-bounded evaluation accounts on top of the platform.
        </li>
      </ul>

      <h2 className="mt-8 text-lg font-semibold text-slate-900">Get in touch</h2>
      <p className="mt-2 text-sm text-slate-600">
        Email <a href="mailto:partnerships@strategylab.in" className="text-blue-600 hover:underline">partnerships@strategylab.in</a>{" "}
        with a short note about your use case. We respond within two business days.
      </p>
    </div>
  );
}
