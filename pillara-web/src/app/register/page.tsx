'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { APIError } from '@/lib/api'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { register } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      await register(email, password)
      // New users always go to onboarding first to set up their profile
      router.push('/onboarding')
    } catch (err) {
      if (err instanceof APIError) {
        if (err.status === 409) {
          setError('An account with this email already exists. Sign in instead?')
        } else {
          setError(err.message)
        }
      } else {
        setError('Something went wrong. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center gap-2 justify-center mb-10">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="text-white font-semibold text-lg">Pillara</span>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
          <h1 className="text-2xl font-bold text-white mb-2">Create your account</h1>
          <p className="text-slate-400 text-sm mb-8">
            Start checking your medications for free.
          </p>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-6">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Password
              </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Min. 8 characters"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 pr-12 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors text-xs"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
              <p className="text-slate-500 text-xs mt-2">
                Must contain uppercase, lowercase, number, and special character.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-lg font-semibold transition-colors text-sm"
            >
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="text-center text-slate-400 text-sm mt-6">
            Already have an account?{' '}
            <Link href="/login" className="text-[#4A9B8E] hover:underline">
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-slate-500 text-xs mt-6 leading-relaxed">
          By creating an account, you agree that Pillara is not a substitute
          for professional medical advice.
        </p>
      </div>
    </div>
  )
}
