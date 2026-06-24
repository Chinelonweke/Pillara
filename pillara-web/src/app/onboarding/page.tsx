'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { profiles, APIError } from '@/lib/api'

// Common allergies for quick-select chips
const COMMON_ALLERGIES = [
  'Penicillin', 'Sulfa', 'Aspirin', 'NSAIDs', 'Codeine',
  'Morphine', 'Ibuprofen', 'Latex', 'Cephalosporins',
]

// Common conditions for quick-select chips
const COMMON_CONDITIONS = [
  'Hypertension', 'Diabetes', 'Asthma', 'Heart disease',
  'Kidney disease', 'Liver disease', 'Thyroid disorder',
  'Epilepsy', 'Depression', 'Anxiety',
]

export default function OnboardingPage() {
  const { user } = useAuth()
  const router = useRouter()

  const [step, setStep] = useState(1) // 2-step flow
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Step 1 — personal info
  const [name, setName] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [gender, setGender] = useState('')
  const [weightKg, setWeightKg] = useState('')

  // Step 2 — health info
  const [selectedAllergies, setSelectedAllergies] = useState<string[]>([])
  const [customAllergy, setCustomAllergy] = useState('')
  const [selectedConditions, setSelectedConditions] = useState<string[]>([])
  const [customCondition, setCustomCondition] = useState('')

  const toggleAllergy = (allergy: string) => {
    setSelectedAllergies(prev =>
      prev.includes(allergy)
        ? prev.filter(a => a !== allergy)
        : [...prev, allergy]
    )
  }

  const toggleCondition = (condition: string) => {
    setSelectedConditions(prev =>
      prev.includes(condition)
        ? prev.filter(c => c !== condition)
        : [...prev, condition]
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

  const handleStep1 = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Please enter your name.')
      return
    }
    setError('')
    setStep(2)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      // Get the primary profile ID
      const profileList = await profiles.list()
      const primaryProfile = profileList.find(p => p.is_primary) || profileList[0]

      if (!primaryProfile) {
        setError('Could not find your profile. Please try again.')
        return
      }

      // Build allergy and condition strings
      const allergyString = selectedAllergies.join(', ')
      const conditionString = selectedConditions.join(', ')

      // Update the profile
      await profiles.update(primaryProfile.id, {
        name: name.trim(),
        date_of_birth: dateOfBirth || undefined,
        gender: gender || undefined,
        weight_kg: weightKg ? parseFloat(weightKg) : undefined,
        known_allergies: allergyString || undefined,
        medical_conditions: conditionString || undefined,
      })

      // WHY RELOAD BEFORE REDIRECT:
      // The backend sets onboarding_completed=true on the User model when
      // the profile is updated with a real name. But the frontend's auth
      // context still holds the old user object with onboarding_completed=false.
      // The dashboard checks this flag and redirects back to /onboarding if
      // it's false — creating a redirect loop. Reloading the page forces the
      // auth context to re-fetch /auth/me with the updated flag.
      window.location.href = '/dashboard'

    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError('Something went wrong. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="flex items-center gap-2 justify-center mb-8">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="text-white font-semibold text-lg">Pillara</span>
        </div>

        {/* Progress */}
        <div className="flex items-center gap-3 mb-8">
          <div className="flex-1 h-1 rounded-full bg-[#4A9B8E]" />
          <div className={`flex-1 h-1 rounded-full transition-colors ${step >= 2 ? 'bg-[#4A9B8E]' : 'bg-white/10'}`} />
        </div>

        {/* Step label */}
        <p className="text-slate-400 text-xs uppercase tracking-widest text-center mb-6">
          Step {step} of 2 — {step === 1 ? 'About you' : 'Your health profile'}
        </p>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-6">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* ── STEP 1: Personal info ─────────────────────────────────────── */}
        {step === 1 && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
            <h1 className="text-2xl font-bold text-white mb-2">Tell us about yourself</h1>
            <p className="text-slate-400 text-sm mb-8">
              This helps Pillara give you more accurate safety information.
            </p>

            <form onSubmit={handleStep1} className="space-y-5">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Full name <span className="text-[#4A9B8E]">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Chinelo Nweke"
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
                />
              </div>

              {/* Date of birth */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Date of birth
                  <span className="text-slate-500 font-normal ml-2">(optional)</span>
                </label>
                <input
                  type="date"
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm [color-scheme:dark]"
                />
              </div>

              {/* Gender */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Gender
                  <span className="text-slate-500 font-normal ml-2">(optional)</span>
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {['Male', 'Female', 'Other'].map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGender(g === gender ? '' : g)}
                      className={`py-2.5 rounded-lg text-sm font-medium transition-colors border ${
                        gender === g
                          ? 'bg-[#4A9B8E] border-[#4A9B8E] text-white'
                          : 'bg-white/5 border-white/10 text-slate-300 hover:border-[#4A9B8E]/50'
                      }`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </div>

              {/* Weight */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Weight (kg)
                  <span className="text-slate-500 font-normal ml-2">(optional)</span>
                </label>
                <input
                  type="number"
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  placeholder="e.g. 70"
                  min="1"
                  max="500"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
                />
              </div>

              <button
                type="submit"
                className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white py-3 rounded-lg font-semibold transition-colors text-sm mt-2"
              >
                Continue →
              </button>
            </form>
          </div>
        )}

        {/* ── STEP 2: Health profile ────────────────────────────────────── */}
        {step === 2 && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-8">
            <h1 className="text-2xl font-bold text-white mb-2">Your health profile</h1>
            <p className="text-slate-400 text-sm mb-2">
              This is what powers Pillara&apos;s allergy cross-reactivity checking.
              Be as specific as possible.
            </p>
            <div className="bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-lg px-4 py-3 mb-6">
              <p className="text-[#4A9B8E] text-xs leading-relaxed">
                Your allergy information is stored securely and never shared.
                It&apos;s used only to flag potentially dangerous medications.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-7">
              {/* Known allergies */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Known drug allergies
                  <span className="text-slate-500 font-normal ml-2">(select all that apply)</span>
                </label>
                <p className="text-slate-500 text-xs mb-3">
                  Pillara uses this to flag cross-reactive drugs automatically.
                </p>

                {/* Quick select chips */}
                <div className="flex flex-wrap gap-2 mb-3">
                  {COMMON_ALLERGIES.map((allergy) => (
                    <button
                      key={allergy}
                      type="button"
                      onClick={() => toggleAllergy(allergy)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                        selectedAllergies.includes(allergy)
                          ? 'bg-[#F59E0B] border-[#F59E0B] text-[#0F1B2D]'
                          : 'bg-white/5 border-white/10 text-slate-300 hover:border-[#F59E0B]/50'
                      }`}
                    >
                      {selectedAllergies.includes(allergy) ? '✓ ' : ''}{allergy}
                    </button>
                  ))}
                </div>

                {/* Custom allergy input */}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customAllergy}
                    onChange={(e) => setCustomAllergy(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomAllergy())}
                    placeholder="Add another allergy…"
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-[#F59E0B] focus:ring-1 focus:ring-[#F59E0B] transition-colors text-sm"
                  />
                  <button
                    type="button"
                    onClick={addCustomAllergy}
                    className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-slate-300 hover:text-white hover:border-white/30 transition-colors text-sm"
                  >
                    Add
                  </button>
                </div>

                {/* Selected custom allergies */}
                {selectedAllergies.filter(a => !COMMON_ALLERGIES.includes(a)).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {selectedAllergies.filter(a => !COMMON_ALLERGIES.includes(a)).map(a => (
                      <span
                        key={a}
                        className="px-3 py-1.5 rounded-full text-xs font-medium bg-[#F59E0B] border border-[#F59E0B] text-[#0F1B2D] flex items-center gap-1"
                      >
                        ✓ {a}
                        <button
                          type="button"
                          onClick={() => toggleAllergy(a)}
                          className="ml-1 opacity-70 hover:opacity-100"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Medical conditions */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">
                  Existing medical conditions
                  <span className="text-slate-500 font-normal ml-2">(select all that apply)</span>
                </label>
                <p className="text-slate-500 text-xs mb-3">
                  Used to flag drug interactions relevant to your health profile.
                </p>

                <div className="flex flex-wrap gap-2 mb-3">
                  {COMMON_CONDITIONS.map((condition) => (
                    <button
                      key={condition}
                      type="button"
                      onClick={() => toggleCondition(condition)}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                        selectedConditions.includes(condition)
                          ? 'bg-[#4A9B8E] border-[#4A9B8E] text-white'
                          : 'bg-white/5 border-white/10 text-slate-300 hover:border-[#4A9B8E]/50'
                      }`}
                    >
                      {selectedConditions.includes(condition) ? '✓ ' : ''}{condition}
                    </button>
                  ))}
                </div>

                {/* Custom condition input */}
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customCondition}
                    onChange={(e) => setCustomCondition(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomCondition())}
                    placeholder="Add another condition…"
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
                  />
                  <button
                    type="button"
                    onClick={addCustomCondition}
                    className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-slate-300 hover:text-white hover:border-white/30 transition-colors text-sm"
                  >
                    Add
                  </button>
                </div>
              </div>

              {/* No allergies option */}
              <div className="flex items-center gap-3 pt-1">
                <input
                  type="checkbox"
                  id="no-allergies"
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedAllergies([])
                      setSelectedConditions([])
                    }
                  }}
                  className="w-4 h-4 accent-[#4A9B8E]"
                />
                <label htmlFor="no-allergies" className="text-slate-400 text-sm">
                  I have no known drug allergies or medical conditions
                </label>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="flex-1 bg-white/5 border border-white/10 hover:bg-white/10 text-slate-300 py-3 rounded-lg font-medium transition-colors text-sm"
                >
                  ← Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-lg font-semibold transition-colors text-sm"
                >
                  {loading ? 'Saving…' : 'Complete setup →'}
                </button>
              </div>
            </form>

            <p className="text-center text-slate-500 text-xs mt-6">
              You can update this information anytime from your profile settings.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
