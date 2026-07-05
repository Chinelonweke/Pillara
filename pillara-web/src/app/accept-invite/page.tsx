'use client'
import { useState, useEffect, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'

function Logo() {
  return (
    <div className="flex items-center gap-2 justify-center mb-10">
      <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
        <span className="text-white font-bold text-sm">P</span>
      </div>
      <span className="text-white font-semibold text-lg">Pillara</span>
    </div>
  )
}

function AcceptInviteForm() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [needsLogin, setNeedsLogin] = useState(false)

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('Invalid invite link. Please ask the profile owner to send you a new one.')
      return
    }
    handleAccept()
  }, [token])

  const handleAccept = async () => {
    if (!token) return
    setStatus('loading')

    try {
      const accessToken = localStorage.getItem('access_token')

      if (!accessToken) {
        setNeedsLogin(true)
        setStatus('idle')
        return
      }

      const response = await fetch('/api/v1/profiles/accept-invite', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ invite_token: token }),
      })

      const data = await response.json()

      if (!response.ok) {
        setStatus('error')
        setMessage(data.detail || 'Failed to accept invite. It may have expired.')
        return
      }

      setStatus('success')
      setMessage(data.message || 'Invite accepted!')
      setTimeout(() => router.push('/dashboard'), 2500)
    } catch {
      setStatus('error')
      setMessage('Something went wrong. Please try again.')
    }
  }

  if (needsLogin) {
    return (
      <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4">
        <div className="w-full max-w-md">
          <Logo />
          <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center">
            <div className="w-12 h-12 bg-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-[#4A9B8E] text-2xl">👋</span>
            </div>
            <h1 className="text-xl font-bold text-white mb-2">Sign in to accept</h1>
            <p className="text-slate-400 text-sm mb-6">
              You need a Pillara account to accept this invitation.
            </p>
            <Link
              href={`/login?redirect=/accept-invite?token=${token}`}
              className="block w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white py-3 rounded-lg font-semibold transition-colors text-sm text-center mb-3"
            >
              Sign in
            </Link>
            <Link
              href={`/register?redirect=/accept-invite?token=${token}`}
              className="block w-full bg-white/10 hover:bg-white/20 text-white py-3 rounded-lg font-semibold transition-colors text-sm text-center"
            >
              Create account
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <Logo />
        <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center">

          {status === 'loading' && (
            <>
              <div className="w-12 h-12 bg-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse">
                <span className="text-[#4A9B8E] text-2xl">⏳</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Accepting invitation...</h1>
              <p className="text-slate-400 text-sm">Just a moment.</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="w-12 h-12 bg-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-[#4A9B8E] text-2xl">✓</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Invitation accepted!</h1>
              <p className="text-slate-400 text-sm">{message}</p>
              <p className="text-slate-500 text-xs mt-3">Redirecting to your dashboard...</p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="w-12 h-12 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-red-400 text-2xl">✕</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Invite not valid</h1>
              <p className="text-slate-400 text-sm mb-6">{message}</p>
              <Link href="/dashboard" className="text-[#4A9B8E] hover:underline text-sm">
                Go to dashboard →
              </Link>
            </>
          )}

        </div>
        <p className="text-center mt-6">
          <Link href="/login" className="text-slate-500 hover:text-slate-300 text-sm transition-colors">
            ← Back to sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center">
        <div className="text-white text-sm">Loading...</div>
      </div>
    }>
      <AcceptInviteForm />
    </Suspense>
  )
}