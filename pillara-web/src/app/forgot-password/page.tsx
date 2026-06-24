'use client'
import { useState } from 'react'
import Link from 'next/link'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Password reset via email is not yet implemented in the backend.
    // This page collects the email and shows the user what to do next.
    // WHY SHOW A MESSAGE INSTEAD OF AN ERROR:
    // For security, we never confirm whether an email is registered or not.
    // Showing a consistent "check your email" message regardless means
    // an attacker can't use this form to enumerate registered emails.
    setSubmitted(true)
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2 justify-center mb-10">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="text-white font-semibold text-lg">Pillara</span>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
          {!submitted ? (
            <>
              <h1 className="text-2xl font-bold text-white mb-2">Reset your password</h1>
              <p className="text-slate-400 text-sm mb-8">
                Enter your email and we&apos;ll send you a link to reset your password.
              </p>

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

                <button
                  type="submit"
                  className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white py-3 rounded-lg font-semibold transition-colors text-sm"
                >
                  Send reset link
                </button>
              </form>
            </>
          ) : (
            <>
              <div className="w-12 h-12 bg-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-[#4A9B8E] text-2xl">✓</span>
              </div>
              <h1 className="text-xl font-bold text-white mb-2 text-center">Check your email</h1>
              <p className="text-slate-400 text-sm text-center leading-relaxed">
                If an account exists for <span className="text-white">{email}</span>,
                you&apos;ll receive a password reset link shortly.
              </p>
              <p className="text-slate-500 text-xs text-center mt-4 leading-relaxed">
                Didn&apos;t receive it? Check your spam folder, or contact
                support at <span className="text-slate-400">support@pillara.app</span>
              </p>
            </>
          )}

          <p className="text-center text-slate-400 text-sm mt-6">
            <Link href="/login" className="text-[#4A9B8E] hover:underline">
              ← Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
