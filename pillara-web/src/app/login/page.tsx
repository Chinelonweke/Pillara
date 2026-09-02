'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { APIError } from '@/lib/api'

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      router.push('/dashboard')
    } catch (err) {
      setError(err instanceof APIError ? err.message : 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{background: 'var(--background)'}}>
      {/* Left panel — branding */}
      <div className="hidden lg:flex flex-col justify-between w-2/5 p-12 relative overflow-hidden"
        style={{background: 'var(--primary)'}}>
        {/* Decorative pill */}
        <div className="absolute -right-12 top-1/3 opacity-20 rotate-45">
          <svg viewBox="0 0 120 48" className="w-64 h-24" fill="none">
            <rect x="2" y="2" width="116" height="44" rx="22" fill="white" stroke="white" strokeWidth="2"/>
            <line x1="60" y1="2" x2="60" y2="46" stroke="white" strokeWidth="2" opacity="0.4"/>
          </svg>
        </div>
        <div className="absolute -left-8 bottom-1/4 opacity-15 -rotate-12">
          <svg viewBox="0 0 48 120" className="w-16 h-40" fill="none">
            <rect x="2" y="2" width="44" height="116" rx="22" fill="white" stroke="white" strokeWidth="2"/>
            <line x1="2" y1="60" x2="46" y2="60" stroke="white" strokeWidth="2" opacity="0.4"/>
          </svg>
        </div>

        <div>
          <div className="flex items-center gap-2 mb-16">
            <div className="w-10 h-10 rounded-xl bg-[var(--surface)]/20 flex items-center justify-center">
              <span className="text-white font-bold">P</span>
            </div>
            <span className="text-white font-bold text-xl">Pillara</span>
          </div>
          <h2 className="text-3xl font-bold text-white mb-4">Your medication safety companion</h2>
          <p className="text-blue-100 leading-relaxed">
            Check interactions, manage profiles, and get AI-powered drug safety information — all in one place.
          </p>
        </div>

        <div className="space-y-4">
          {[
            { icon: '✓', text: 'Drug interaction detection' },
            { icon: '✓', text: 'Allergy cross-reactivity alerts' },
            { icon: '✓', text: 'Multi-patient caregiver profiles' },
            { icon: '✓', text: 'Verified FDA + RxNorm data' },
          ].map(({ icon, text }) => (
            <div key={text} className="flex items-center gap-3">
              <div className="w-6 h-6 rounded-full bg-[var(--surface)]/20 flex items-center justify-center text-xs text-white font-bold">
                {icon}
              </div>
              <span className="text-blue-100 text-sm">{text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{background: 'var(--primary)'}}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-bold text-lg" style={{color: 'var(--foreground)'}}>Pillara</span>
          </div>

          <h1 className="text-2xl font-bold mb-1" style={{color: 'var(--foreground)'}}>Welcome back</h1>
          <p className="text-sm mb-8" style={{color: 'var(--muted)'}}>
            Sign in to check your medications.
          </p>

          {error && (
            <div className="p-3 rounded-xl mb-6 text-sm" style={{background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626'}}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{color: 'var(--foreground)'}}>
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{
                  background: 'var(--surface)',
                  border: '1.5px solid var(--border)',
                  color: 'var(--foreground)',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                onBlur={e => e.target.style.borderColor = 'var(--border)'}
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-sm font-medium" style={{color: 'var(--foreground)'}}>Password</label>
                <Link href="/forgot-password" className="text-xs" style={{color: 'var(--primary)'}}>
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all pr-12"
                  style={{
                    background: 'var(--surface)',
                    border: '1.5px solid var(--border)',
                    color: 'var(--foreground)',
                  }}
                  onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border)'}
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs"
                  style={{color: 'var(--muted)'}}>
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl text-white font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-50 mt-2"
              style={{background: 'var(--primary)'}}>
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <p className="text-center text-sm mt-6" style={{color: 'var(--muted)'}}>
            Don&apos;t have an account?{' '}
            <Link href="/register" className="font-semibold" style={{color: 'var(--primary)'}}>
              Create one free
            </Link>
          </p>

          <p className="text-center text-xs mt-8" style={{color: 'var(--muted)'}}>
            By signing in, you agree to our{' '}
            <Link href="/terms" style={{color: 'var(--primary)'}}>Terms</Link>{' '}
            and{' '}
            <Link href="/privacy" style={{color: 'var(--primary)'}}>Privacy Policy</Link>
          </p>
        </div>
      </div>
    </div>
  )
}