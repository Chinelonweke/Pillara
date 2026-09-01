'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { APIError } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function RegisterPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new APIError(res.status, data.error, data.message || 'Registration failed')
      localStorage.setItem('pillara_access_token', data.access_token)
      if (data.refresh_token) localStorage.setItem('pillara_refresh_token', data.refresh_token)
      router.push('/onboarding')
    } catch (err) {
      setError(err instanceof APIError ? err.message : 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const strength = password.length === 0 ? 0 : password.length < 6 ? 1 : password.length < 10 ? 2 : 3

  return (
    <div className="min-h-screen flex" style={{background: 'var(--background)'}}>
      {/* Left panel */}
      <div className="hidden lg:flex flex-col justify-between w-2/5 p-12 relative overflow-hidden"
        style={{background: 'linear-gradient(135deg, #0D9488 0%, #0F766E 100%)'}}>
        <div className="absolute -right-8 top-1/4 opacity-20 rotate-12">
          <svg viewBox="0 0 48 120" className="w-16 h-40" fill="none">
            <rect x="2" y="2" width="44" height="116" rx="22" fill="white" stroke="white" strokeWidth="2"/>
            <line x1="2" y1="60" x2="46" y2="60" stroke="white" strokeWidth="2" opacity="0.4"/>
            <rect x="2" y="2" width="44" height="58" rx="22" fill="white" opacity="0.3"/>
          </svg>
        </div>

        <div>
          <div className="flex items-center gap-2 mb-16">
            <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
              <span className="text-white font-bold">P</span>
            </div>
            <span className="text-white font-bold text-xl">Pillara</span>
          </div>
          <h2 className="text-3xl font-bold text-white mb-4">Start your medication safety journey</h2>
          <p className="text-teal-100 leading-relaxed">
            Join thousands of Nigerians managing their medications safely with AI-powered insights.
          </p>
        </div>

        <div className="p-5 rounded-2xl" style={{background: 'rgba(255,255,255,0.1)', backdropFilter: 'blur(10px)'}}>
          <p className="text-white text-sm font-semibold mb-3">✓ What you get</p>
          <div className="space-y-2">
            {['Free forever for personal use', 'Unlimited medication profiles', 'AI-powered drug interaction checks', 'Caregiver sharing with role controls'].map(item => (
              <p key={item} className="text-teal-100 text-xs">{item}</p>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{background: 'var(--primary)'}}>
              <span className="text-white font-bold text-sm">P</span>
            </div>
            <span className="font-bold text-lg" style={{color: 'var(--foreground)'}}>Pillara</span>
          </div>

          <h1 className="text-2xl font-bold mb-1" style={{color: 'var(--foreground)'}}>Create your account</h1>
          <p className="text-sm mb-8" style={{color: 'var(--muted)'}}>Free forever. No credit card required.</p>

          {error && (
            <div className="p-3 rounded-xl mb-6 text-sm" style={{background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626'}}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{color: 'var(--foreground)'}}>Email address</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} required
                placeholder="you@example.com"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{background: 'var(--surface)', border: '1.5px solid var(--border)', color: 'var(--foreground)'}}
                onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                onBlur={e => e.target.style.borderColor = 'var(--border)'}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5" style={{color: 'var(--foreground)'}}>Password</label>
              <div className="relative">
                <input type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} required
                  placeholder="Minimum 8 characters"
                  className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all pr-12"
                  style={{background: 'var(--surface)', border: '1.5px solid var(--border)', color: 'var(--foreground)'}}
                  onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border)'}
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs" style={{color: 'var(--muted)'}}>
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
              {password.length > 0 && (
                <div className="mt-2 flex gap-1">
                  {[1,2,3].map(i => (
                    <div key={i} className="h-1 flex-1 rounded-full transition-all"
                      style={{background: i <= strength ? (strength === 1 ? '#EF4444' : strength === 2 ? '#F59E0B' : '#10B981') : 'var(--border)'}} />
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5" style={{color: 'var(--foreground)'}}>Confirm password</label>
              <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required
                placeholder="Repeat your password"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{
                  background: 'var(--surface)',
                  border: `1.5px solid ${confirmPassword && confirmPassword !== password ? '#EF4444' : 'var(--border)'}`,
                  color: 'var(--foreground)'
                }}
                onFocus={e => e.target.style.borderColor = confirmPassword !== password ? '#EF4444' : 'var(--primary)'}
                onBlur={e => e.target.style.borderColor = confirmPassword && confirmPassword !== password ? '#EF4444' : 'var(--border)'}
              />
              {confirmPassword && confirmPassword !== password && (
                <p className="text-xs mt-1" style={{color: '#EF4444'}}>Passwords do not match</p>
              )}
            </div>

            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl text-white font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-50 mt-2"
              style={{background: 'var(--primary)'}}>
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>

          <p className="text-center text-sm mt-6" style={{color: 'var(--muted)'}}>
            Already have an account?{' '}
            <Link href="/login" className="font-semibold" style={{color: 'var(--primary)'}}>Sign in</Link>
          </p>

          <p className="text-center text-xs mt-6" style={{color: 'var(--muted)'}}>
            By creating an account, you agree to our{' '}
            <Link href="/terms" style={{color: 'var(--primary)'}}>Terms</Link>{' '}
            and{' '}
            <Link href="/privacy" style={{color: 'var(--primary)'}}>Privacy Policy</Link>
          </p>
        </div>
      </div>
    </div>
  )
}