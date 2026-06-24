'use client'
import Link from 'next/link'

export default function Home() {
  return (
    <div className="min-h-screen bg-[#0F1B2D] text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-8 py-6 max-w-6xl mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="font-semibold text-lg">Pillara</span>
        </div>
        <div className="flex items-center gap-4">
          <Link
            href="/login"
            className="text-slate-300 hover:text-white transition-colors text-sm"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <main className="max-w-6xl mx-auto px-8 pt-20 pb-32">
        <div className="max-w-3xl">
          {/* Eyebrow */}
          <div className="inline-flex items-center gap-2 bg-[#4A9B8E]/10 border border-[#4A9B8E]/30 rounded-full px-4 py-1.5 mb-8">
            <div className="w-2 h-2 bg-[#4A9B8E] rounded-full" />
            <span className="text-[#4A9B8E] text-sm font-medium">AI-powered medication safety</span>
          </div>

          <h1 className="text-5xl font-bold leading-tight mb-6 text-white">
            Know before you take.
          </h1>

          <p className="text-xl text-slate-400 leading-relaxed mb-10 max-w-2xl">
            Pillara checks your medications for dangerous interactions and allergy
            cross-reactivity. Built on verified clinical data, never guessing —
            for patients and the people who care for them.
          </p>

          <div className="flex items-center gap-4">
            <Link
              href="/register"
              className="bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-8 py-3.5 rounded-lg font-semibold transition-colors"
            >
              Check your medications
            </Link>
            <Link
              href="/login"
              className="text-slate-300 hover:text-white transition-colors font-medium"
            >
              Already have an account →
            </Link>
          </div>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-24">
          {[
            {
              icon: '⚠️',
              title: 'Allergy cross-reactivity',
              description:
                'Penicillin allergy? Pillara flags amoxicillin, cephalosporins, and every drug in the same class — automatically.',
            },
            {
              icon: '🔍',
              title: 'Drug interaction check',
              description:
                'Check up to 10 drugs at once against verified FDA data. If the evidence is thin, Pillara says so instead of guessing.',
            },
            {
              icon: '💬',
              title: 'Ask about your medications',
              description:
                'Plain-language answers to your medication questions, grounded in real clinical data with a confidence gate on every response.',
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="bg-white/5 border border-white/10 rounded-xl p-6 hover:bg-white/8 transition-colors"
            >
              <div className="text-2xl mb-4">{feature.icon}</div>
              <h3 className="font-semibold text-white mb-2">{feature.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>

        {/* Safety note */}
        <div className="mt-16 border border-[#F59E0B]/20 bg-[#F59E0B]/5 rounded-xl p-6">
          <div className="flex items-start gap-3">
            <span className="text-[#F59E0B] text-lg mt-0.5">🛡️</span>
            <div>
              <p className="text-[#F59E0B] font-medium text-sm mb-1">Not a substitute for medical advice</p>
              <p className="text-slate-400 text-sm leading-relaxed">
                Pillara surfaces safety information and flags known risks. Always discuss medication
                decisions with your doctor or pharmacist. When Pillara doesn&apos;t have verified data,
                it tells you — it never fabricates a confident answer.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
