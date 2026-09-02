import Link from 'next/link'

export default function AboutPage() {
  return (
    <div className="min-h-screen text-[var(--foreground)]" style={{background: "var(--background)"}}>
      {/* Nav */}
      <nav className="border-b border-[var(--border)] px-6 md:px-12 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[var(--primary)] rounded-lg flex items-center justify-center">
              <span className="text-[var(--foreground)] font-bold text-sm">P</span>
            </div>
            <span className="text-[var(--foreground)] font-semibold text-lg">Pillara</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">Sign in</Link>
            <Link href="/register" className="bg-[var(--primary)] hover:bg-[#3d8a7d] text-[var(--foreground)] px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              Get started
            </Link>
          </div>
        </div>
      </nav>

      <main className="px-6 md:px-12 py-16 max-w-3xl mx-auto">
        <h1 className="text-4xl font-bold text-[var(--foreground)] mb-4">About Pillara</h1>
        <p className="text-[var(--muted)] text-lg leading-relaxed mb-12">
          Medication errors kill. Most are preventable with better information.
        </p>

        <div className="space-y-12 text-[var(--foreground)] text-sm leading-7">
          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-xl mb-4">The problem we&apos;re solving</h2>
            <p>
              Polypharmacy — taking multiple medications at the same time — is one of the leading causes of
              preventable hospital admissions worldwide. In many regions where pharmacist density is low and
              self-medication is common, patients frequently combine medications without knowing the risks.
            </p>
            <p className="mt-3">
              A caregiver managing an elderly parent&apos;s medications has no easy way to check whether
              amoxicillin interacts with the blood pressure medication their parent has been on for years.
              A nurse in a busy ward needs a fast second opinion on a drug combination and has no time to
              search through package inserts.
            </p>
            <p className="mt-3">
              Pillara was built to close that gap.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-xl mb-4">How we built it</h2>
            <p>
              Pillara uses a retrieval-augmented generation (RAG) pipeline — the same architecture
              used by enterprise medical AI systems. Every answer is grounded in verified data from
              the FDA and RxNorm, the US National Library of Medicine&apos;s drug terminology system.
            </p>
            <p className="mt-3">
              When you ask about a drug interaction, Pillara does not ask the AI to recall from its training.
              Instead it searches 541+ verified drug knowledge chunks, re-ranks them for relevance using a
              clinical cross-encoder model, and only then asks the AI to explain what the verified data says.
            </p>
            <p className="mt-3">
              If the retrieved data is not confident enough — below our 0.75 confidence threshold — Pillara
              refuses to answer rather than guess. For a medication safety product, a safe &quot;I don&apos;t know&quot;
              is better than a confident wrong answer.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-xl mb-4">Our commitment to privacy</h2>
            <p>
              Your medication list is among the most sensitive data you have. We treat it that way.
            </p>
            <ul className="space-y-2 list-disc list-inside mt-3">
              <li>Your name and email are never sent to AI providers — only drug names and your questions</li>
              <li>Personal health information is scrubbed from all error logs before leaving our servers</li>
              <li>Every action on your data is recorded in a tamper-evident audit log</li>
              <li>Sessions are verified server-side on every request — logging out actually works</li>
              <li>You can delete your account and all data at any time from Settings</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-xl mb-4">What Pillara is not</h2>
            <div className="bg-[#F59E0B]/5 border border-[#F59E0B]/20 rounded-xl p-4">
              <p>
                Pillara is an informational tool. It does not replace your doctor, pharmacist, or any
                qualified healthcare professional. It does not diagnose, prescribe, or treat.
                The information it provides is a starting point for a conversation with your healthcare
                provider — not a substitute for one.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-xl mb-4">Contact</h2>
            <p>Questions, feedback, or partnership inquiries:</p>
            <a href="mailto:hello@pillara.site" className="text-[var(--primary)] hover:underline">hello@pillara.site</a>
            <p className="mt-2">Privacy and data requests:</p>
            <a href="mailto:privacy@pillara.site" className="text-[var(--primary)] hover:underline">privacy@pillara.site</a>
          </section>
        </div>

        <div className="mt-16 pt-8 border-t border-[var(--border)] flex gap-6">
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">← Home</Link>
          <Link href="/privacy" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">Privacy Policy</Link>
          <Link href="/terms" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">Terms of Service</Link>
        </div>
      </main>
    </div>
  )
}