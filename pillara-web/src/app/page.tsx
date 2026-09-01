import Link from 'next/link'

// Pill SVG illustration component
function PillIllustration({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 120 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="2" width="116" height="44" rx="22" fill="url(#pillGrad)" stroke="#2563EB" strokeWidth="2"/>
      <line x1="60" y1="2" x2="60" y2="46" stroke="#2563EB" strokeWidth="2" opacity="0.3"/>
      <rect x="2" y="2" width="58" height="44" rx="22" fill="#2563EB" opacity="0.15"/>
      <defs>
        <linearGradient id="pillGrad" x1="0" y1="0" x2="120" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#EFF6FF"/>
          <stop offset="1" stopColor="#DBEAFE"/>
        </linearGradient>
      </defs>
    </svg>
  )
}

function CapsuleIllustration({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="2" width="44" height="116" rx="22" fill="url(#capGrad)" stroke="#0D9488" strokeWidth="2"/>
      <line x1="2" y1="60" x2="46" y2="60" stroke="#0D9488" strokeWidth="2" opacity="0.3"/>
      <rect x="2" y="2" width="44" height="58" rx="22" fill="#0D9488" opacity="0.2"/>
      <defs>
        <linearGradient id="capGrad" x1="0" y1="0" x2="48" y2="120" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F0FDFA"/>
          <stop offset="1" stopColor="#CCFBF1"/>
        </linearGradient>
      </defs>
    </svg>
  )
}

function TabletIllustration({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="40" cy="40" r="38" fill="url(#tabGrad)" stroke="#2563EB" strokeWidth="2"/>
      <line x1="2" y1="40" x2="78" y2="40" stroke="#2563EB" strokeWidth="2" opacity="0.2"/>
      <circle cx="40" cy="40" r="12" fill="#2563EB" opacity="0.15"/>
      <defs>
        <linearGradient id="tabGrad" x1="0" y1="0" x2="80" y2="80" gradientUnits="userSpaceOnUse">
          <stop stopColor="#EFF6FF"/>
          <stop offset="1" stopColor="#BFDBFE"/>
        </linearGradient>
      </defs>
    </svg>
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen" style={{background: '#F8FAFF', color: 'var(--foreground)'}}>

      {/* Top announcement bar */}
      <div style={{background: 'var(--primary)', color: 'white'}} className="text-center py-2 text-xs font-medium">
        Built for patients and caregivers everywhere — NDPR compliant · Free to use
      </div>

      {/* Navigation */}
      <nav style={{background: 'var(--surface)', borderBottom: '1px solid var(--border)'}} className="sticky top-0 z-50 px-6 md:px-12 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{background: 'var(--primary)'}}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-bold text-lg" style={{color: 'var(--foreground)'}}>Pillara</span>
          </div>
          <div className="hidden md:flex items-center gap-8">
            <a href="#features" className="text-sm transition-colors hover:opacity-80" style={{color: 'var(--muted)'}}>Features</a>
            <a href="#how-it-works" className="text-sm transition-colors hover:opacity-80" style={{color: 'var(--muted)'}}>How it works</a>
            <a href="#safety" className="text-sm transition-colors hover:opacity-80" style={{color: 'var(--muted)'}}>Safety</a>
            <Link href="/about" className="text-sm transition-colors hover:opacity-80" style={{color: 'var(--muted)'}}>About</Link>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-medium transition-colors" style={{color: 'var(--primary)'}}>Sign in</Link>
            <Link href="/register"
              className="px-5 py-2 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90"
              style={{background: 'var(--primary)'}}>
              Get started free
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden px-6 md:px-12 pt-16 pb-24">
        {/* Background decorative pills */}
        <div className="absolute top-10 right-10 opacity-10 rotate-12 pointer-events-none" style={{zIndex: 0}}>
          <PillIllustration className="w-48 h-20" />
        </div>
        <div className="absolute bottom-10 -left-6 opacity-10 -rotate-12 pointer-events-none" style={{zIndex: 0}}>
          <CapsuleIllustration className="w-12 h-32" />
        </div>
        <div className="absolute top-1/2 right-1/3 opacity-8 rotate-45 pointer-events-none" style={{zIndex: 0}}>
          <TabletIllustration className="w-16 h-16" />
        </div>

        <div className="max-w-6xl mx-auto relative" style={{zIndex: 1}}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            {/* Left — Copy */}
            <div>
              <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium mb-6"
                style={{background: 'var(--primary-light)', color: 'var(--primary)', border: '1px solid #BFDBFE'}}>
                <span className="w-2 h-2 rounded-full animate-pulse" style={{background: 'var(--primary)'}} />
                AI-powered medication safety
              </div>

              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight mb-6" style={{color: 'var(--foreground)'}}>
                Know what your<br />
                <span style={{color: 'var(--primary)'}}>medications</span><br />
                do to each other
              </h1>

              <p className="text-lg leading-relaxed mb-8 max-w-lg" style={{color: 'var(--muted)'}}>
                Pillara checks your full medication list for dangerous interactions, allergy conflicts,
                and safety risks — using verified FDA and RxNorm clinical data, not guesswork.
              </p>

              <div className="flex flex-col sm:flex-row gap-4 mb-10">
                <Link href="/register"
                  className="px-8 py-4 rounded-2xl text-white font-semibold text-base text-center"
                  style={{background: '#2563EB', boxShadow: '0 4px 14px rgba(37,99,235,0.4)', display: 'block'}}>
                  Check my medications — free
                </Link>
                <a href="#how-it-works"
                  className="px-8 py-4 rounded-2xl font-semibold text-base transition-all hover:opacity-80 text-center"
                  style={{border: '1.5px solid var(--border)', color: 'var(--foreground)', background: 'var(--surface)'}}>
                  See how it works →
                </a>
              </div>

              {/* Trust stats */}
              <div className="grid grid-cols-3 gap-6">
                {[
                  { n: '541+', label: 'Drug knowledge chunks' },
                  { n: '3-layer', label: 'Allergy detection' },
                  { n: 'NDPR', label: 'Compliant' },
                ].map(({ n, label }) => (
                  <div key={label}>
                    <p className="text-xl font-bold" style={{color: 'var(--primary)'}}>{n}</p>
                    <p className="text-xs mt-0.5" style={{color: 'var(--muted)'}}>{label}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Right — App preview card */}
            <div className="relative">
              {/* Floating pill decorations */}
              <div className="absolute -top-6 -right-4 rotate-12">
                <PillIllustration className="w-32 h-14" />
              </div>
              <div className="absolute -bottom-4 -left-4 -rotate-12">
                <CapsuleIllustration className="w-10 h-28" />
              </div>
              <div className="absolute top-1/4 -right-8 rotate-45">
                <TabletIllustration className="w-16 h-16" />
              </div>

              {/* Mock app card */}
              <div className="rounded-3xl p-6 relative z-10"
                style={{background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--border)'}}>
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <p className="font-bold text-sm" style={{color: 'var(--foreground)'}}>My Medications</p>
                    <p className="text-xs" style={{color: 'var(--muted)'}}>4 active · Safety check ready</p>
                  </div>
                  <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{background: 'var(--primary-light)'}}>
                    <span style={{color: 'var(--primary)'}}>💊</span>
                  </div>
                </div>

                {[
                  { name: 'Metformin', dose: '500mg', color: '#2563EB', safe: true },
                  { name: 'Lisinopril', dose: '10mg', color: '#0D9488', safe: true },
                  { name: 'Ibuprofen', dose: '400mg', color: '#EF4444', safe: false },
                  { name: 'Warfarin', dose: '5mg', color: '#F59E0B', safe: true },
                ].map((med) => (
                  <div key={med.name} className="flex items-center justify-between py-3"
                    style={{borderBottom: '1px solid var(--border)'}}>
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold text-white"
                        style={{background: med.color}}>
                        {med.name[0]}
                      </div>
                      <div>
                        <p className="text-sm font-medium" style={{color: 'var(--foreground)'}}>{med.name}</p>
                        <p className="text-xs" style={{color: 'var(--muted)'}}>{med.dose}</p>
                      </div>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded-full font-medium`}
                      style={{
                        background: med.safe ? '#F0FDF4' : '#FEF2F2',
                        color: med.safe ? '#16A34A' : '#DC2626'
                      }}>
                      {med.safe ? '✓ Safe' : '⚠ Check'}
                    </span>
                  </div>
                ))}

                {/* Risk badge */}
                <div className="mt-4 p-3 rounded-2xl flex items-center gap-3"
                  style={{background: '#FEF2F2', border: '1px solid #FECACA'}}>
                  <span className="text-lg">⚠️</span>
                  <div>
                    <p className="text-xs font-semibold" style={{color: '#DC2626'}}>Interaction detected</p>
                    <p className="text-xs" style={{color: '#EF4444'}}>Ibuprofen + Warfarin — high risk</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="px-6 md:px-12 py-20"
        style={{scrollMarginTop: '80px', background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)'}}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-sm font-semibold uppercase tracking-widest mb-3" style={{color: 'var(--primary)'}}>How it works</p>
            <h2 className="text-3xl md:text-4xl font-bold" style={{color: 'var(--foreground)'}}>
              From medication list to safety report in seconds
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 relative">
            {[
              { step: '1', icon: '💊', title: 'Add your medications', desc: 'Enter generic names, brand names, or describe your pills. Pillara understands both.' },
              { step: '2', icon: '🔍', title: 'AI retrieves clinical data', desc: 'Searches 541+ verified FDA and RxNorm drug knowledge chunks using semantic AI search.' },
              { step: '3', icon: '⚡', title: 'Cross-encoder reranking', desc: 'A clinical reranking model surfaces the most relevant safety information for your specific combination.' },
              { step: '4', icon: '📋', title: 'Clear safety report', desc: 'Risk level, specific interactions, allergy warnings — in plain language you can act on.' },
            ].map(({ step, icon, title, desc }, i) => (
              <div key={step} className="relative text-center">
                {i < 3 && (
                  <div className="hidden md:block absolute top-8 left-full w-full h-px z-0"
                    style={{background: 'linear-gradient(to right, var(--border), transparent)'}} />
                )}
                <div className="relative z-10 inline-flex items-center justify-center w-16 h-16 rounded-2xl text-2xl mb-4"
                  style={{background: 'var(--primary-light)', border: '1.5px solid #BFDBFE'}}>
                  {icon}
                </div>
                <div className="w-6 h-6 rounded-full text-xs font-bold text-white flex items-center justify-center mx-auto mb-3"
                  style={{background: 'var(--primary)', marginTop: '-8px', position: 'relative', zIndex: 10}}>
                  {step}
                </div>
                <h3 className="font-semibold text-sm mb-2" style={{color: 'var(--foreground)'}}>{title}</h3>
                <p className="text-xs leading-relaxed" style={{color: 'var(--muted)'}}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" style={{scrollMarginTop: '80px'}} className="px-6 md:px-12 py-20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-sm font-semibold uppercase tracking-widest mb-3" style={{color: 'var(--primary)'}}>Features</p>
            <h2 className="text-3xl md:text-4xl font-bold mb-4" style={{color: 'var(--foreground)'}}>
              Everything you need to stay safe
            </h2>
            <p className="max-w-xl mx-auto" style={{color: 'var(--muted)'}}>
              Built for patients, caregivers, and healthcare workers who need reliable medication information — fast.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              { icon: '⚡', title: 'Drug interaction check', desc: 'Instantly check dangerous combinations from your full medication list. Grounded in verified FDA data.', color: '#EFF6FF', border: '#BFDBFE' },
              { icon: '🧬', title: '3-layer allergy detection', desc: 'Cross-checks drug classes, molecular families, and cross-reactive compounds — not just name matching.', color: '#F0FDFA', border: '#99F6E4' },
              { icon: '🤖', title: 'AI medication assistant', desc: 'Ask anything in plain language. The AI only answers from verified clinical knowledge and refuses to guess.', color: '#EFF6FF', border: '#BFDBFE' },
              { icon: '👥', title: 'Multi-patient profiles', desc: 'Manage medications for your whole family. Invite caregivers with owner, caregiver, or viewer access.', color: '#F0FDFA', border: '#99F6E4' },
              { icon: '⏰', title: 'Medication reminders', desc: 'Set email reminders for each medication. Every reminder is logged in your notification history.', color: '#EFF6FF', border: '#BFDBFE' },
              { icon: '🔒', title: 'Privacy first', desc: 'PHI scrubbed from all logs. Sessions verified server-side on every request. NDPR compliant.', color: '#F0FDFA', border: '#99F6E4' },
            ].map(({ icon, title, desc, color, border }) => (
              <div key={title} className="p-6 rounded-2xl transition-all hover:scale-[1.02]"
                style={{background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow)'}}>
                <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl mb-4"
                  style={{background: color, border: `1.5px solid ${border}`}}>
                  {icon}
                </div>
                <h3 className="font-semibold mb-2" style={{color: 'var(--foreground)'}}>{title}</h3>
                <p className="text-sm leading-relaxed" style={{color: 'var(--muted)'}}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section className="px-6 md:px-12 py-20"
        style={{background: 'var(--primary)', color: 'white'}}>
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Built for everyone managing medications
            </h2>
            <p className="text-blue-100 max-w-xl mx-auto">
              Whether you are a patient, caregiver, or healthcare worker — Pillara works for you.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: '🧑',
                title: 'Patients',
                desc: 'Managing your own medications across multiple prescriptions? Get clarity on what each drug does and whether they are safe together.',
                tag: 'Self-care',
              },
              {
                icon: '👨‍👩‍👧',
                title: 'Family caregivers',
                desc: 'Looking after an elderly parent? Create profiles for each person, invite other caregivers, and stay on top of their medication safety.',
                tag: 'Caregiver',
              },
              {
                icon: '🏥',
                title: 'Healthcare workers',
                desc: 'Need a fast second opinion on a drug combination? Pillara surfaces verified clinical evidence in seconds.',
                tag: 'Clinical',
              },
            ].map(({ icon, title, desc, tag }) => (
              <div key={title} className="p-6 rounded-2xl"
                style={{background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', backdropFilter: 'blur(10px)'}}>
                <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold mb-4"
                  style={{background: 'rgba(255,255,255,0.2)', color: 'white'}}>
                  {tag}
                </span>
                <div className="text-4xl mb-3">{icon}</div>
                <h3 className="text-white font-bold text-lg mb-2">{title}</h3>
                <p className="text-blue-100 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Safety disclaimer */}
      <section id="safety" className="px-6 md:px-12 py-10" style={{scrollMarginTop: "80px"}}>
        <div className="max-w-4xl mx-auto">
          <div className="p-5 rounded-2xl flex gap-4 items-start"
            style={{background: '#FFFBEB', border: '1px solid #FDE68A'}}>
            <span className="text-2xl flex-shrink-0">⚠️</span>
            <p className="text-sm leading-relaxed" style={{color: '#92400E'}}>
              <strong style={{color: '#78350F'}}>Pillara is an informational tool, not a medical authority.</strong>{' '}
              Always consult your doctor or pharmacist before making any decisions about your medications.
              Pillara does not provide medical advice, diagnosis, or treatment recommendations.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 md:px-12 py-20" style={{background: 'var(--surface)'}}>
        <div className="max-w-3xl mx-auto text-center relative overflow-hidden">
          {/* Decorative pills */}
          <div className="absolute top-0 right-0 opacity-10 rotate-12">
            <PillIllustration className="w-40 h-16" />
          </div>
          <div className="absolute bottom-0 left-0 opacity-10 -rotate-12">
            <CapsuleIllustration className="w-12 h-32" />
          </div>

          <div className="relative z-10">
            <h2 className="text-3xl md:text-4xl font-bold mb-4" style={{color: 'var(--foreground)'}}>
              Start checking your medications today
            </h2>
            <p className="mb-8" style={{color: 'var(--muted)'}}>
              Free to use. No credit card. Your data stays yours.
            </p>
            <Link href="/register"
              className="inline-block px-10 py-4 rounded-2xl text-white font-semibold text-base transition-all hover:opacity-90"
              style={{background: 'var(--primary)', boxShadow: '0 4px 20px rgba(37,99,235,0.4)'}}>
              Create free account
            </Link>
            <p className="text-xs mt-4" style={{color: 'var(--muted)'}}>
              NDPR compliant
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{background: 'var(--foreground)', color: 'white'}} className="px-6 md:px-12 py-12">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{background: 'var(--primary)'}}>
                  <span className="text-white font-bold text-xs">P</span>
                </div>
                <span className="font-bold text-white">Pillara</span>
              </div>
              <p className="text-xs leading-relaxed" style={{color: '#9CA3AF'}}>
                AI-powered medication safety for patients, caregivers, and healthcare workers everywhere.
              </p>
            </div>
            <div>
              <p className="text-sm font-semibold text-white mb-3">Product</p>
              <div className="space-y-2">
                {['Features', 'How it works', 'Get started', 'Sign in'].map(item => (
                  <div key={item}>
                    <Link href={item === 'Get started' ? '/register' : item === 'Sign in' ? '/login' : `#${item.toLowerCase().replace(' ', '-')}`}
                      className="text-xs transition-colors hover:text-white" style={{color: '#9CA3AF'}}>
                      {item}
                    </Link>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold text-white mb-3">Company</p>
              <div className="space-y-2">
                <div><Link href="/about" className="text-xs hover:text-white" style={{color: '#9CA3AF'}}>About</Link></div>
                <div><a href="mailto:hello@pillara.site" className="text-xs hover:text-white" style={{color: '#9CA3AF'}}>Contact</a></div>
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold text-white mb-3">Legal</p>
              <div className="space-y-2">
                <div><Link href="/privacy" className="text-xs hover:text-white" style={{color: '#9CA3AF'}}>Privacy Policy</Link></div>
                <div><Link href="/terms" className="text-xs hover:text-white" style={{color: '#9CA3AF'}}>Terms of Service</Link></div>
              </div>
            </div>
          </div>
          <div className="pt-6 flex flex-col md:flex-row items-center justify-between gap-4"
            style={{borderTop: '1px solid #374151'}}>
            <p className="text-xs" style={{color: '#6B7280'}}>© 2026 Pillara Health. All rights reserved.</p>
            <p className="text-xs" style={{color: '#6B7280'}}></p>
          </div>
        </div>
      </footer>
    </div>
  )
}