import Link from 'next/link'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0F1B2D] text-white">
      {/* Navigation */}
      <nav className="border-b border-white/10 px-6 md:px-12 py-4 sticky top-0 bg-[#0F1B2D]/95 backdrop-blur-sm z-50">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="text-white font-semibold text-lg">Pillara</span>
          </div>
          <div className="hidden md:flex items-center gap-8">
            <Link href="#features" className="text-slate-400 hover:text-white text-sm transition-colors">Features</Link>
            <Link href="#how-it-works" className="text-slate-400 hover:text-white text-sm transition-colors">How it works</Link>
            <Link href="/about" className="text-slate-400 hover:text-white text-sm transition-colors">About</Link>
            <Link href="/privacy" className="text-slate-400 hover:text-white text-sm transition-colors">Privacy</Link>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-slate-400 hover:text-white text-sm transition-colors">Sign in</Link>
            <Link href="/register" className="bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              Get started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-6 md:px-12 py-24 md:py-36">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-full px-4 py-1.5 mb-8">
            <div className="w-2 h-2 bg-[#4A9B8E] rounded-full animate-pulse" />
            <span className="text-[#4A9B8E] text-sm font-medium">AI-powered medication safety</span>
          </div>

          <h1 className="text-4xl md:text-6xl font-bold text-white leading-tight mb-6">
            Know what your{' '}
            <span className="text-[#4A9B8E]">medications</span>{' '}
            are doing to each other
          </h1>

          <p className="text-slate-400 text-lg md:text-xl leading-relaxed max-w-2xl mx-auto mb-10">
            Pillara checks your medication list for dangerous interactions, allergy conflicts, and safety risks — 
            using verified clinical data, not guesswork.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/register"
              className="w-full sm:w-auto bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-8 py-3.5 rounded-xl font-semibold text-base transition-colors"
            >
              Check my medications — it&apos;s free
            </Link>
            <Link
              href="#how-it-works"
              className="w-full sm:w-auto bg-white/5 hover:bg-white/10 border border-white/10 text-white px-8 py-3.5 rounded-xl font-medium text-base transition-colors"
            >
              See how it works
            </Link>
          </div>

          <p className="text-slate-600 text-xs mt-6">No credit card required · Your data is never sold</p>
        </div>
      </section>

      {/* Trust bar */}
      <section className="border-y border-white/5 px-6 md:px-12 py-8 bg-white/2">
        <div className="max-w-4xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            {[
              { stat: '541+', label: 'Drug knowledge chunks' },
              { stat: '3-layer', label: 'Allergy detection' },
              { stat: '99.9%', label: 'Uptime target' },
              { stat: 'NDPR', label: 'Compliant' },
            ].map(({ stat, label }) => (
              <div key={label}>
                <p className="text-[#4A9B8E] text-2xl font-bold">{stat}</p>
                <p className="text-slate-500 text-xs mt-1">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-6 md:px-12 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Everything you need to stay safe
            </h2>
            <p className="text-slate-400 max-w-xl mx-auto">
              Built for patients, caregivers, and healthcare workers who need reliable medication information — fast.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                icon: '⚡',
                title: 'Drug interaction check',
                desc: 'Add your medications and instantly check for dangerous combinations. Results are grounded in verified FDA and RxNorm clinical data.',
              },
              {
                icon: '🧬',
                title: '3-layer allergy detection',
                desc: 'Cross-checks your known allergies against drug classes, molecular families, and cross-reactive compounds — not just surface-level name matching.',
              },
              {
                icon: '🤖',
                title: 'AI medication assistant',
                desc: 'Ask anything about your medications in plain language. The AI only answers from verified clinical knowledge — it refuses to guess.',
              },
              {
                icon: '👥',
                title: 'Multi-patient profiles',
                desc: 'Manage medications for your whole family or patients under your care. Invite caregivers with role-based access control.',
              },
              {
                icon: '⏰',
                title: 'Medication reminders',
                desc: 'Set email reminders for each medication. Never miss a dose. Every reminder is logged in your notification history.',
              },
              {
                icon: '🔒',
                title: 'Built for privacy',
                desc: 'Your health data never leaves secure servers. PHI is scrubbed from all logs. Sessions are cryptographically verified on every request.',
              },
            ].map(({ icon, title, desc }) => (
              <div key={title} className="bg-white/5 border border-white/10 rounded-2xl p-6 hover:border-[#4A9B8E]/30 transition-colors">
                <div className="text-3xl mb-4">{icon}</div>
                <h3 className="text-white font-semibold mb-2">{title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 md:px-12 py-24 bg-white/2 border-y border-white/5">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">How Pillara works</h2>
            <p className="text-slate-400">From your medication list to a safety report in seconds.</p>
          </div>

          <div className="space-y-8">
            {[
              {
                step: '01',
                title: 'Add your medications',
                desc: 'Enter the medications you or your patient is taking. Generic names, brand names — Pillara understands both.',
              },
              {
                step: '02',
                title: 'Run a safety check',
                desc: 'Pillara searches 541+ verified drug knowledge chunks using semantic AI search, then re-ranks results for maximum accuracy.',
              },
              {
                step: '03',
                title: 'Get a clear safety report',
                desc: 'See your overall risk level, specific interactions found, and allergy warnings — with a source-grounded explanation in plain language.',
              },
              {
                step: '04',
                title: 'Ask the AI anything',
                desc: 'Not sure what a drug class is? Ask. The AI only answers from verified clinical data and tells you when it doesn\'t know.',
              },
            ].map(({ step, title, desc }) => (
              <div key={step} className="flex gap-6 items-start">
                <div className="w-12 h-12 bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-xl flex items-center justify-center flex-shrink-0">
                  <span className="text-[#4A9B8E] font-bold text-sm">{step}</span>
                </div>
                <div className="pt-1">
                  <h3 className="text-white font-semibold mb-1">{title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section className="px-6 md:px-12 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">Built for everyone managing medications</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                title: 'Patients',
                desc: 'Managing your own medications across multiple prescriptions? Pillara gives you clarity on what each drug does and whether they\'re safe together.',
                icon: '🧑',
              },
              {
                title: 'Family caregivers',
                desc: 'Looking after an elderly parent or family member? Create profiles for each person, invite other caregivers, and stay on top of their medication safety.',
                icon: '👨‍👩‍👧',
              },
              {
                title: 'Healthcare workers',
                desc: 'Need a fast second opinion on a drug combination? Pillara surfaces verified clinical evidence in seconds — with citations from FDA and RxNorm data.',
                icon: '🏥',
              },
            ].map(({ title, desc, icon }) => (
              <div key={title} className="bg-white/5 border border-white/10 rounded-2xl p-6">
                <div className="text-4xl mb-4">{icon}</div>
                <h3 className="text-white font-semibold text-lg mb-3">{title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Safety disclaimer */}
      <section className="px-6 md:px-12 py-12">
        <div className="max-w-4xl mx-auto">
          <div className="bg-[#F59E0B]/5 border border-[#F59E0B]/20 rounded-2xl px-6 py-5 flex gap-4">
            <span className="text-[#F59E0B] text-xl flex-shrink-0">⚠️</span>
            <p className="text-slate-400 text-sm leading-relaxed">
              <strong className="text-slate-300">Pillara is an informational tool, not a medical authority.</strong>{' '}
              Always consult your doctor or pharmacist before making any decisions about your medications.
              Pillara does not provide medical advice, diagnosis, or treatment recommendations.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 md:px-12 py-24">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
            Start checking your medications today
          </h2>
          <p className="text-slate-400 mb-8">
            Free to use. No credit card. Your data stays yours.
          </p>
          <Link
            href="/register"
            className="inline-block bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-10 py-4 rounded-xl font-semibold text-base transition-colors"
          >
            Create free account
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 px-6 md:px-12 py-12">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-7 h-7 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold text-xs">P</span>
                </div>
                <span className="text-white font-semibold">Pillara</span>
              </div>
              <p className="text-slate-500 text-xs leading-relaxed">
                AI-powered medication safety for patients, caregivers, and healthcare workers.
              </p>
            </div>
            <div>
              <p className="text-white text-sm font-medium mb-3">Product</p>
              <div className="space-y-2">
                <Link href="#features" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Features</Link>
                <Link href="#how-it-works" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">How it works</Link>
                <Link href="/register" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Get started</Link>
                <Link href="/login" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Sign in</Link>
              </div>
            </div>
            <div>
              <p className="text-white text-sm font-medium mb-3">Company</p>
              <div className="space-y-2">
                <Link href="/about" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">About</Link>
                <a href="mailto:hello@pillara.site" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Contact</a>
              </div>
            </div>
            <div>
              <p className="text-white text-sm font-medium mb-3">Legal</p>
              <div className="space-y-2">
                <Link href="/privacy" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Privacy Policy</Link>
                <Link href="/terms" className="block text-slate-500 hover:text-slate-300 text-xs transition-colors">Terms of Service</Link>
              </div>
            </div>
          </div>
          <div className="border-t border-white/5 pt-6 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-slate-600 text-xs">© 2026 Pillara Health. All rights reserved.</p>
            <p className="text-slate-600 text-xs">Built in Nigeria 🇳🇬</p>
          </div>
        </div>
      </footer>
    </div>
  )
}