'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth-context'
import { profiles, Profile, APIError } from '@/lib/api'

const COMMON_ALLERGIES = [
  'Penicillin', 'Sulfa', 'Aspirin', 'NSAIDs', 'Codeine',
  'Morphine', 'Ibuprofen', 'Latex', 'Cephalosporins',
]

const COMMON_CONDITIONS = [
  'Hypertension', 'Diabetes', 'Asthma', 'Heart disease',
  'Kidney disease', 'Liver disease', 'Thyroid disorder',
  'Epilepsy', 'Depression', 'Anxiety',
]

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

  const [profile, setProfile] = useState<Profile | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  // Account management state
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [showDeleteAccount, setShowDeleteAccount] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const [deletePassword, setDeletePassword] = useState('')
  const [accountActionLoading, setAccountActionLoading] = useState(false)
  const [accountActionMsg, setAccountActionMsg] = useState('')
  const [accountActionError, setAccountActionError] = useState('')

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword !== confirmNewPassword) {
      setAccountActionError('New passwords do not match.')
      return
    }
    if (newPassword.length < 8) {
      setAccountActionError('New password must be at least 8 characters.')
      return
    }
    setAccountActionLoading(true)
    setAccountActionError('')
    setAccountActionMsg('')
    try {
      const token = localStorage.getItem('pillara_access_token')
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/auth/change-password`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      const data = await res.json()
      if (!res.ok) { setAccountActionError(data.message || 'Failed to change password.'); return }
      setAccountActionMsg('Password changed successfully.')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmNewPassword('')
      setShowChangePassword(false)
    } catch { setAccountActionError('Something went wrong. Please try again.') }
    finally { setAccountActionLoading(false) }
  }

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setAccountActionLoading(true)
    setAccountActionError('')
    try {
      const token = localStorage.getItem('pillara_access_token')
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/auth/account`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: deletePassword }),
      })
      const data = await res.json()
      if (!res.ok) { setAccountActionError(data.message || 'Failed to delete account.'); return }
      localStorage.clear()
      router.push('/')
    } catch { setAccountActionError('Something went wrong. Please try again.') }
    finally { setAccountActionLoading(false) }
  }

  // Dark mode state — initialized directly from localStorage to avoid setState-in-effect lint error
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem('pillara_dark_mode') === 'true'
  })

  const toggleDarkMode = () => {
    const newValue = !darkMode
    setDarkMode(newValue)
    localStorage.setItem('pillara_dark_mode', String(newValue))
    document.documentElement.setAttribute('data-theme', newValue ? 'dark' : 'light')
  }

  // Form fields
  const [name, setName] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [gender, setGender] = useState('')
  const [weightKg, setWeightKg] = useState('')
  const [selectedAllergies, setSelectedAllergies] = useState<string[]>([])
  const [customAllergy, setCustomAllergy] = useState('')
  const [selectedConditions, setSelectedConditions] = useState<string[]>([])
  const [customCondition, setCustomCondition] = useState('')

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
    }
  }, [user, authLoading, router])

  // Load current profile data and pre-fill the form
  useEffect(() => {
    if (!user) return

    profiles.list()
      .then((profileList) => {
        const primary = profileList.find(p => p.is_primary) || profileList[0]
        if (primary) {
          setProfile(primary)

          // Pre-fill form with current values
          setName(primary.name === 'Me' ? '' : primary.name || '')
          setDateOfBirth(
            primary.date_of_birth
              ? primary.date_of_birth.split('T')[0]  // strip time if present
              : ''
          )
          setGender(primary.gender || '')
          setWeightKg(primary.weight_kg ? String(primary.weight_kg) : '')

          // Parse comma-separated allergies into array
          if (primary.known_allergies) {
            const allergyList = primary.known_allergies
              .split(',')
              .map(a => a.trim())
              .filter(Boolean)
            setSelectedAllergies(allergyList)
          }

          // Parse comma-separated conditions into array
          if (primary.medical_conditions) {
            const conditionList = primary.medical_conditions
              .split(',')
              .map(c => c.trim())
              .filter(Boolean)
            setSelectedConditions(conditionList)
          }
        }
      })
      .catch(console.error)
      .finally(() => setLoadingProfile(false))
  }, [user])

  const toggleAllergy = (allergy: string) => {
    setSelectedAllergies(prev =>
      prev.includes(allergy) ? prev.filter(a => a !== allergy) : [...prev, allergy]
    )
  }

  const toggleCondition = (condition: string) => {
    setSelectedConditions(prev =>
      prev.includes(condition) ? prev.filter(c => c !== condition) : [...prev, condition]
    )
  }

  const addCustomAllergy = () => {
    const trimmed = customAllergy.trim()
    if (trimmed && !selectedAllergies.includes(trimmed)) {
      setSelectedAllergies(prev => [...prev, trimmed])
    }
    setCustomAllergy('')
  }

  const addCustomCondition = () => {
    const trimmed = customCondition.trim()
    if (trimmed && !selectedConditions.includes(trimmed)) {
      setSelectedConditions(prev => [...prev, trimmed])
    }
    setCustomCondition('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile) return
    if (!name.trim()) {
      setError('Name is required.')
      return
    }

    setSaving(true)
    setError('')
    setSaved(false)

    try {
      await profiles.update(profile.id, {
        name: name.trim(),
        date_of_birth: dateOfBirth || undefined,
        gender: gender || undefined,
        weight_kg: weightKg ? parseFloat(weightKg) : undefined,
        known_allergies: selectedAllergies.join(', ') || undefined,
        medical_conditions: selectedConditions.join(', ') || undefined,
      })
      setSaved(true)
      // Show success briefly, then go back to dashboard
      setTimeout(() => router.push('/dashboard'), 1500)
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError('Failed to save. Please try again.')
      }
    } finally {
      setSaving(false)
    }
  }

  if (authLoading || loadingProfile) {
    return (
      <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <p className="text-[var(--muted)] text-sm">Loading your profile…</p>
      </div>
    )
  }

  if (!user) return null

  return (
    <div className="min-h-screen bg-[var(--background)]">
      {/* Nav */}
      <nav className="border-b border-[var(--border)] px-8 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors text-sm">
              ← Dashboard
            </Link>
            <span className="text-[var(--foreground)]/20">/</span>
            <span className="text-[var(--foreground)] text-sm font-medium">Profile settings</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[var(--primary)] rounded-lg flex items-center justify-center">
              <span className="text-[var(--foreground)] font-bold text-xs">P</span>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-2xl mx-auto px-8 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[var(--foreground)] mb-2">Profile settings</h1>
          <p className="text-[var(--muted)] text-sm">
            Keep your health information up to date for accurate safety checks.
            Changes take effect immediately on your next medication check.
          </p>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-6">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {saved && (
          <div className="bg-[var(--primary)]/10 border border-[var(--primary)]/30 rounded-lg px-4 py-3 mb-6">
            <p className="text-[var(--primary)] text-sm">✓ Profile saved. Redirecting to dashboard…</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Personal info */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6">
            <h2 className="text-[var(--foreground)] font-semibold mb-5">Personal information</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[var(--foreground)] mb-2">
                  Full name <span className="text-[var(--primary)]">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Chinelo Nweke"
                  required
                  className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-3 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--foreground)] mb-2">
                    Date of birth
                  </label>
                  <input
                    type="date"
                    value={dateOfBirth}
                    onChange={(e) => setDateOfBirth(e.target.value)}
                    className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-3 text-[var(--foreground)] focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm [color-scheme:dark]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--foreground)] mb-2">
                    Weight (kg)
                  </label>
                  <input
                    type="number"
                    value={weightKg}
                    onChange={(e) => setWeightKg(e.target.value)}
                    placeholder="e.g. 70"
                    min="1"
                    max="500"
                    className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-3 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Gender</label>
                <div className="grid grid-cols-3 gap-2">
                  {['Male', 'Female', 'Other'].map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGender(g === gender ? '' : g)}
                      className={`py-2.5 rounded-lg text-sm font-medium transition-colors border ${
                        gender === g
                          ? 'bg-[var(--primary)] border-[var(--primary)] text-[var(--foreground)]'
                          : 'bg-[var(--surface)] border-[var(--border)] text-[var(--foreground)] hover:border-[var(--primary)]/50'
                      }`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Allergies */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6">
            <div className="flex items-start justify-between mb-1">
              <h2 className="text-[var(--foreground)] font-semibold">Known drug allergies</h2>
              {selectedAllergies.length > 0 && (
                <span className="text-[#F59E0B] text-xs bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-full px-2 py-0.5">
                  {selectedAllergies.length} selected
                </span>
              )}
            </div>
            <p className="text-[var(--muted)] text-xs mb-4">
              Pillara uses this to flag cross-reactive drugs automatically.
              Update this immediately if you discover a new allergy.
            </p>

            <div className="flex flex-wrap gap-2 mb-3">
              {COMMON_ALLERGIES.map((allergy) => (
                <button
                  key={allergy}
                  type="button"
                  onClick={() => toggleAllergy(allergy)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                    selectedAllergies.includes(allergy)
                      ? 'bg-[#F59E0B] border-[#F59E0B] text-[#0F1B2D]'
                      : 'bg-[var(--surface)] border-[var(--border)] text-[var(--foreground)] hover:border-[#F59E0B]/50'
                  }`}
                >
                  {selectedAllergies.includes(allergy) ? '✓ ' : ''}{allergy}
                </button>
              ))}
            </div>

            {/* Custom allergies that aren't in common list */}
            {selectedAllergies.filter(a => !COMMON_ALLERGIES.includes(a)).length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {selectedAllergies.filter(a => !COMMON_ALLERGIES.includes(a)).map(a => (
                  <span
                    key={a}
                    className="px-3 py-1.5 rounded-full text-xs font-medium bg-[#F59E0B] border border-[#F59E0B] text-[#0F1B2D] flex items-center gap-1"
                  >
                    ✓ {a}
                    <button type="button" onClick={() => toggleAllergy(a)} className="ml-1 opacity-70 hover:opacity-100">×</button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="text"
                value={customAllergy}
                onChange={(e) => setCustomAllergy(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomAllergy())}
                placeholder="Add another allergy…"
                className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[#F59E0B] focus:ring-1 focus:ring-[#F59E0B] transition-colors text-sm"
              />
              <button
                type="button"
                onClick={addCustomAllergy}
                className="px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-lg text-[var(--foreground)] hover:text-[var(--foreground)] transition-colors text-sm"
              >
                Add
              </button>
            </div>
          </div>

          {/* Medical conditions */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6">
            <div className="flex items-start justify-between mb-1">
              <h2 className="text-[var(--foreground)] font-semibold">Medical conditions</h2>
              {selectedConditions.length > 0 && (
                <span className="text-[var(--primary)] text-xs bg-[var(--primary)]/10 border border-[var(--primary)]/20 rounded-full px-2 py-0.5">
                  {selectedConditions.length} selected
                </span>
              )}
            </div>
            <p className="text-[var(--muted)] text-xs mb-4">
              Existing diagnoses that affect which medications are safe for you.
              These are separate from allergies — they describe your health
              conditions, not substances you react to.
            </p>

            <div className="flex flex-wrap gap-2 mb-3">
              {COMMON_CONDITIONS.map((condition) => (
                <button
                  key={condition}
                  type="button"
                  onClick={() => toggleCondition(condition)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                    selectedConditions.includes(condition)
                      ? 'bg-[var(--primary)] border-[var(--primary)] text-[var(--foreground)]'
                      : 'bg-[var(--surface)] border-[var(--border)] text-[var(--foreground)] hover:border-[var(--primary)]/50'
                  }`}
                >
                  {selectedConditions.includes(condition) ? '✓ ' : ''}{condition}
                </button>
              ))}
            </div>

            {selectedConditions.filter(c => !COMMON_CONDITIONS.includes(c)).length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {selectedConditions.filter(c => !COMMON_CONDITIONS.includes(c)).map(c => (
                  <span
                    key={c}
                    className="px-3 py-1.5 rounded-full text-xs font-medium bg-[var(--primary)] border border-[var(--primary)] text-[var(--foreground)] flex items-center gap-1"
                  >
                    ✓ {c}
                    <button type="button" onClick={() => toggleCondition(c)} className="ml-1 opacity-70 hover:opacity-100">×</button>
                  </span>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <input
                type="text"
                value={customCondition}
                onChange={(e) => setCustomCondition(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomCondition())}
                placeholder="Add another condition…"
                className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm"
              />
              <button
                type="button"
                onClick={addCustomCondition}
                className="px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-lg text-[var(--foreground)] hover:text-[var(--foreground)] transition-colors text-sm"
              >
                Add
              </button>
            </div>
          </div>

          {/* Save */}
          <div className="flex gap-3">
            <Link
              href="/dashboard"
              className="flex-1 text-center bg-[var(--surface)] border border-[var(--border)] hover:bg-[var(--primary-light)] text-[var(--foreground)] py-3 rounded-lg font-medium transition-colors text-sm"
            >
              Cancel
            </Link>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--foreground)] py-3 rounded-lg font-semibold transition-colors text-sm"
            >
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </main>
          {/* Account */}
          <div className="rounded-xl border border-[var(--border)] overflow-hidden" style={{background: 'var(--surface)'}}>
            <div className="px-5 py-4 border-b border-[var(--border)]">
              <h2 className="font-semibold text-sm" style={{color: 'var(--foreground)'}}>Account</h2>
            </div>
            <div className="divide-y divide-[var(--border)]">
              <div className="px-5 py-4">
                {accountActionMsg && (
                  <div className="mb-3 p-3 rounded-lg text-sm" style={{background: 'var(--primary-light)', color: 'var(--primary)'}}>✓ {accountActionMsg}</div>
                )}
                {accountActionError && (
                  <div className="mb-3 p-3 rounded-lg text-sm" style={{background: '#FEF2F2', color: '#DC2626'}}>{accountActionError}</div>
                )}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium" style={{color: 'var(--foreground)'}}>Change password</p>
                    <p className="text-xs mt-0.5" style={{color: 'var(--muted)'}}>Update your account password</p>
                  </div>
                  <button type="button" onClick={() => { setShowChangePassword(!showChangePassword); setAccountActionError(''); setAccountActionMsg('') }}
                    className="text-sm font-medium" style={{color: 'var(--primary)'}}>
                    {showChangePassword ? 'Cancel' : 'Change'}
                  </button>
                </div>
                {showChangePassword && (
                  <form onSubmit={handleChangePassword} className="mt-4 space-y-3">
                    <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
                      required placeholder="Current password"
                      className="w-full px-4 py-2.5 rounded-xl text-sm outline-none"
                      style={{background: 'var(--background)', border: '1.5px solid var(--border)', color: 'var(--foreground)'}} />
                    <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
                      required placeholder="New password (min 8 characters)"
                      className="w-full px-4 py-2.5 rounded-xl text-sm outline-none"
                      style={{background: 'var(--background)', border: '1.5px solid var(--border)', color: 'var(--foreground)'}} />
                    <input type="password" value={confirmNewPassword} onChange={e => setConfirmNewPassword(e.target.value)}
                      required placeholder="Confirm new password"
                      className="w-full px-4 py-2.5 rounded-xl text-sm outline-none"
                      style={{background: 'var(--background)', border: '1.5px solid var(--border)', color: 'var(--foreground)'}} />
                    <button type="submit" disabled={accountActionLoading}
                      className="w-full py-2.5 rounded-xl text-white text-sm font-semibold"
                      style={{background: 'var(--primary)'}}>
                      {accountActionLoading ? 'Changing...' : 'Update password'}
                    </button>
                  </form>
                )}
              </div>
              <div className="px-5 py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium" style={{color: '#DC2626'}}>Delete account</p>
                    <p className="text-xs mt-0.5" style={{color: 'var(--muted)'}}>Permanently delete your account and all data</p>
                  </div>
                  <button type="button" onClick={() => { setShowDeleteAccount(!showDeleteAccount); setAccountActionError('') }}
                    className="text-sm font-medium" style={{color: '#DC2626'}}>
                    {showDeleteAccount ? 'Cancel' : 'Delete'}
                  </button>
                </div>
                {showDeleteAccount && (
                  <form onSubmit={handleDeleteAccount} className="mt-4 space-y-3">
                    <div className="p-3 rounded-xl text-xs" style={{background: '#FEF2F2', color: '#DC2626'}}>
                      ⚠️ This is permanent and cannot be undone. All your profiles, medications, reminders, and data will be deleted.
                    </div>
                    <input type="password" value={deletePassword} onChange={e => setDeletePassword(e.target.value)}
                      required placeholder="Enter your password to confirm"
                      className="w-full px-4 py-2.5 rounded-xl text-sm outline-none"
                      style={{background: 'var(--background)', border: '1.5px solid #FCA5A5', color: 'var(--foreground)'}} />
                    <button type="submit" disabled={accountActionLoading}
                      className="w-full py-2.5 rounded-xl text-white text-sm font-semibold"
                      style={{background: '#DC2626'}}>
                      {accountActionLoading ? 'Deleting...' : 'Permanently delete my account'}
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>

          {/* App Preferences */}
          <div className="rounded-xl border border-[var(--border)] overflow-hidden" style={{background: 'var(--surface)'}}>
            <div className="px-5 py-4 border-b border-[var(--border)]">
              <h2 className="font-semibold text-sm" style={{color: 'var(--foreground)'}}>App preferences</h2>
            </div>
            <div className="px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium" style={{color: 'var(--foreground)'}}>Dark mode</p>
                  <p className="text-xs mt-0.5" style={{color: 'var(--muted)'}}>Switch between light and dark theme</p>
                </div>
                <button
                  type="button"
                  onClick={toggleDarkMode}
                  className="relative w-12 h-6 rounded-full transition-colors duration-200 focus:outline-none"
                  style={{background: darkMode ? 'var(--primary)' : 'var(--border)'}}
                >
                  <span
                    className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200"
                    style={{transform: darkMode ? 'translateX(24px)' : 'translateX(0)'}}
                  />
                </button>
              </div>
            </div>
          </div>

    </div>
  )
}