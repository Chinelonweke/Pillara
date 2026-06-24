'use client'
import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { auth, APIError } from '@/lib/api'

export default function VerifyEmailPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('No verification token found. Check the link in your email.')
      return
    }

    auth.verifyEmail(token)
      .then(() => {
        setStatus('success')
        // Redirect to dashboard after 2 seconds
        setTimeout(() => router.push('/dashboard'), 2000)
      })
      .catch((err) => {
        setStatus('error')
        if (err instanceof APIError) {
          setMessage(err.message)
        } else {
          setMessage('Verification failed. The link may have expired.')
        }
      })
  }, [token, router])

  return (
    <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4">
      <div className="w-full max-w-md text-center">
        <div className="flex items-center gap-2 justify-center mb-10">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="text-white font-semibold text-lg">Pillara</span>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
          {status === 'verifying' && (
            <>
              <div className="w-10 h-10 border-2 border-[#4A9B8E] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <h1 className="text-xl font-bold text-white mb-2">Verifying your email…</h1>
              <p className="text-slate-400 text-sm">Just a moment.</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="w-12 h-12 bg-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-[#4A9B8E] text-2xl">✓</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Email verified</h1>
              <p className="text-slate-400 text-sm">
                You now have full access to Pillara. Redirecting you to your dashboard…
              </p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="w-12 h-12 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-red-400 text-2xl">✗</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Verification failed</h1>
              <p className="text-slate-400 text-sm mb-6">
                {message || 'Something went wrong. Try again or contact support.'}
              </p>
              <Link
                href="/dashboard"
                className="inline-block bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
              >
                Go to dashboard
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
