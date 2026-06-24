'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { profiles, medications, interactions, ai, Profile, Medication, InteractionCheckResponse, APIError } from '@/lib/api'

// Strip markdown symbols from LLM-generated text before display.
// WHY: LLMs occasionally ignore plain-text instructions and generate
// markdown. In a healthcare UI, **bold** rendering as literal asterisks
// looks unprofessional and erodes trust. This is a defensive fallback —
// the prompt already instructs the LLM to avoid markdown.
function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')   // **bold** → bold
    .replace(/\*(.*?)\*/g, '$1')        // *italic* → italic
    .replace(/^#{1,6}\s+/gm, '')        // ## headers → plain text
    .replace(/^[\*\-]\s+/gm, '')        // * bullet or - bullet → plain
    .replace(/^\d+\.\s+/gm, '')         // 1. numbered list → plain
    .trim()
}

export default function DashboardPage() {
  const { user, logout, loading: authLoading } = useAuth()
  const router = useRouter()

  const [profile, setProfile] = useState<Profile | null>(null)
  const [meds, setMeds] = useState<Medication[]>([])
  const [loadingData, setLoadingData] = useState(true)

  // Add medication form
  const [newMedName, setNewMedName] = useState('')
  const [newMedDosage, setNewMedDosage] = useState('')
  const [addingMed, setAddingMed] = useState(false)
  const [addMedError, setAddMedError] = useState('')

  // Interaction check
  const [checkResult, setCheckResult] = useState<InteractionCheckResponse | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState('')

  // AI Chat
  const [chatMessages, setChatMessages] = useState<{role: 'user' | 'assistant', content: string}[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)

  // Redirect to login if not authenticated, onboarding if not completed
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
    }
    if (!authLoading && user && !user.onboarding_completed) {
      router.push('/onboarding')
    }
  }, [user, authLoading, router])

  // Load profile and medications
  useEffect(() => {
    if (!user) return

    const loadData = async () => {
      try {
        const profileList = await profiles.list()
        const primaryProfile = profileList.find(p => p.is_primary) || profileList[0]
        if (primaryProfile) {
          setProfile(primaryProfile)
          const medList = await medications.list(primaryProfile.id)
          setMeds(medList)
        }
      } catch (err) {
        console.error('Failed to load profile data:', err)
      } finally {
        setLoadingData(false)
      }
    }

    loadData()
  }, [user])

  const handleAddMedication = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile || !newMedName.trim()) return

    setAddingMed(true)
    setAddMedError('')

    try {
      const newMed = await medications.add(profile.id, {
        name: newMedName.trim(),
        dosage: newMedDosage.trim() || undefined,
      })
      setMeds(prev => [...prev, newMed])
      setNewMedName('')
      setNewMedDosage('')
    } catch (err) {
      if (err instanceof APIError) {
        setAddMedError(err.message)
      } else {
        setAddMedError('Failed to add medication. Please try again.')
      }
    } finally {
      setAddingMed(false)
    }
  }

  const handleInteractionCheck = async () => {
    if (!profile || meds.length < 1) return

    setChecking(true)
    setCheckError('')
    setCheckResult(null)

    try {
      const drugNames = meds.map(m => m.name)
      // Need at least 2 drugs — add a placeholder if only one
      const drugsToCheck = drugNames.length >= 2 ? drugNames : [...drugNames, ...drugNames]
      const result = await interactions.check(drugsToCheck.slice(0, 10), profile.id)
      setCheckResult(result)
    } catch (err) {
      if (err instanceof APIError) {
        setCheckError(err.message)
      } else {
        setCheckError('Interaction check failed. Please try again.')
      }
    } finally {
      setChecking(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    router.push('/')
  }

  const handleChatSend = async () => {
    if (!chatInput.trim() || chatLoading) return

    const userMessage = chatInput.trim()
    setChatInput('')
    setChatError('')
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setChatLoading(true)

    // Scroll to bottom after adding message
    setTimeout(() => {
      const el = document.getElementById('chat-messages')
      if (el) el.scrollTop = el.scrollHeight
    }, 50)

    try {
      const result = await ai.query(
        userMessage,
        profile?.id,
        conversationId,
      )
      setConversationId(result.conversation_id)
      setChatMessages(prev => [...prev, { role: 'assistant', content: result.response_text }])

      // Scroll to bottom after response
      setTimeout(() => {
        const el = document.getElementById('chat-messages')
        if (el) el.scrollTop = el.scrollHeight
      }, 50)
    } catch (err) {
      if (err instanceof APIError) {
        setChatError(err.message)
      } else {
        setChatError('Failed to get a response. Please try again.')
      }
      // Remove the user message if the request failed
      setChatMessages(prev => prev.slice(0, -1))
    } finally {
      setChatLoading(false)
    }
  }

  if (authLoading || loadingData) {
    return (
      <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center">
        <div className="text-slate-400 text-sm">Loading your medications…</div>
      </div>
    )
  }

  if (!user) return null

  const riskColor = {
    high: 'text-red-400 bg-red-500/10 border-red-500/20',
    moderate: 'text-[#F59E0B] bg-[#F59E0B]/10 border-[#F59E0B]/20',
    low: 'text-green-400 bg-green-500/10 border-green-500/20',
    none: 'text-green-400 bg-green-500/10 border-green-500/20',
    unknown: 'text-slate-400 bg-slate-500/10 border-slate-500/20',
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D]">
      {/* Top nav */}
      <nav className="border-b border-white/10 px-8 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xs">P</span>
            </div>
            <span className="text-white font-semibold">Pillara</span>
          </div>
          <div className="flex items-center gap-4">
            {!user.is_verified && (
              <div className="flex items-center gap-2 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-lg px-3 py-1.5">
                <span className="text-[#F59E0B] text-xs">⚠️ Check your email to verify your account</span>
              </div>
            )}
            <Link
              href="/settings"
              className="text-slate-400 hover:text-white text-sm transition-colors"
            >
              Settings
            </Link>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-white text-sm transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-8 py-10">
        {/* Profile header */}
        <div className="mb-10">
          <h1 className="text-2xl font-bold text-white mb-1">
            {profile?.name || 'My Medications'}
          </h1>
          {profile?.known_allergies && (
            <div className="flex items-center gap-2 mt-3">
              <span className="text-xs text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-full px-3 py-1">
                ⚠️ Allergy: {profile.known_allergies}
              </span>
            </div>
          )}
          {profile?.medical_conditions && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-slate-400 bg-white/5 border border-white/10 rounded-full px-3 py-1">
                Condition: {profile.medical_conditions}
              </span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left: Medications */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Current medications</h2>
              <span className="text-slate-400 text-xs">{meds.length} total</span>
            </div>

            {/* Medication list */}
            <div className="space-y-3 mb-6">
              {meds.length === 0 ? (
                <div className="bg-white/5 border border-white/10 border-dashed rounded-xl p-8 text-center">
                  <p className="text-slate-400 text-sm">No medications added yet.</p>
                  <p className="text-slate-500 text-xs mt-1">Add your first medication below.</p>
                </div>
              ) : (
                meds.map(med => (
                  <div
                    key={med.id}
                    className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 flex items-center justify-between"
                  >
                    <div>
                      <p className="text-white text-sm font-medium capitalize">{med.name}</p>
                      {med.dosage && (
                        <p className="text-slate-400 text-xs mt-0.5">{med.dosage}</p>
                      )}
                    </div>
                    <div className="w-2 h-2 bg-[#4A9B8E] rounded-full" />
                  </div>
                ))
              )}
            </div>

            {/* Add medication form */}
            <div className="bg-white/5 border border-white/10 rounded-xl p-5">
              <h3 className="text-white text-sm font-medium mb-4">Add medication</h3>

              {addMedError && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 mb-4">
                  <p className="text-red-400 text-xs">{addMedError}</p>
                </div>
              )}

              <form onSubmit={handleAddMedication} className="space-y-3">
                <input
                  type="text"
                  value={newMedName}
                  onChange={(e) => setNewMedName(e.target.value)}
                  placeholder="Medication name (e.g. amoxicillin)"
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
                />
                <input
                  type="text"
                  value={newMedDosage}
                  onChange={(e) => setNewMedDosage(e.target.value)}
                  placeholder="Dosage (optional, e.g. 500mg)"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm"
                />
                <button
                  type="submit"
                  disabled={addingMed || !newMedName.trim()}
                  className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-medium transition-colors"
                >
                  {addingMed ? 'Adding…' : 'Add medication'}
                </button>
              </form>
            </div>
          </div>

          {/* Right: Interaction check */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Safety check</h2>
            </div>

            <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-4">
              <p className="text-slate-400 text-sm mb-4 leading-relaxed">
                Check all your current medications for dangerous interactions
                and allergy cross-reactivity.
              </p>
              <button
                onClick={handleInteractionCheck}
                disabled={checking || meds.length === 0}
                className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-lg text-sm font-semibold transition-colors"
              >
                {checking ? 'Checking…' : `Check ${meds.length} medication${meds.length !== 1 ? 's' : ''}`}
              </button>
              {meds.length === 0 && (
                <p className="text-slate-500 text-xs mt-2 text-center">Add at least one medication first.</p>
              )}
            </div>

            {checkError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-4">
                <p className="text-red-400 text-sm">{checkError}</p>
              </div>
            )}

            {checkResult && (
              <div className="space-y-4">
                {/* Overall risk */}
                <div className={`border rounded-xl px-4 py-3 ${riskColor[checkResult.overall_risk as keyof typeof riskColor] || riskColor.unknown}`}>
                  <p className="text-xs font-medium uppercase tracking-wide mb-1 opacity-70">Overall risk</p>
                  <p className="font-semibold capitalize">{checkResult.overall_risk}</p>
                </div>

                {/* Allergy warnings — always shown prominently */}
                {checkResult.allergy_warnings.length > 0 && (
                  <div className="bg-[#F59E0B]/10 border border-[#F59E0B]/30 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-[#F59E0B]">⚠️</span>
                      <p className="text-[#F59E0B] font-semibold text-sm">
                        {checkResult.allergy_warnings.length} allergy warning{checkResult.allergy_warnings.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                    {checkResult.allergy_warnings.map((warning, i) => (
                      <div key={i} className="mb-3 last:mb-0">
                        <p className="text-white text-sm font-medium capitalize mb-1">
                          {warning.drug_name} — {warning.allergen} allergy
                        </p>
                        <p className="text-slate-300 text-xs leading-relaxed mb-2">{warning.description}</p>
                        <p className="text-[#F59E0B] text-xs font-medium">{warning.action_required}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Summary */}
                <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <p className="text-slate-300 text-xs font-medium mb-3 uppercase tracking-wide">Analysis</p>
                  <p className="text-slate-300 text-sm leading-7">{stripMarkdown(checkResult.summary)}</p>
                </div>

                {/* Disclaimer */}
                <p className="text-slate-500 text-xs leading-relaxed px-1">
                  {checkResult.disclaimer}
                </p>

                {/* Confidence indicator */}
                <div className="flex items-center gap-2 px-1">
                  <div className={`w-2 h-2 rounded-full ${checkResult.confidence_gate_passed ? 'bg-[#4A9B8E]' : 'bg-slate-500'}`} />
                  <p className="text-slate-500 text-xs">
                    {checkResult.confidence_gate_passed
                      ? 'Response grounded in verified clinical data'
                      : 'Insufficient verified data — consult your pharmacist'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* AI Chat Interface */}
        <div className="mt-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-white font-semibold">Ask the medication assistant</h2>
              <p className="text-slate-500 text-xs mt-1">
                Ask about drug classes, adverse effects, interactions, or how medications work.
                Grounded in verified clinical data.
              </p>
            </div>
          </div>

          <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
            {/* Chat messages */}
            <div className="h-80 overflow-y-auto p-4 space-y-4" id="chat-messages">
              {chatMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-8">
                  <div className="w-12 h-12 bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-full flex items-center justify-center mb-4">
                    <span className="text-[#4A9B8E] text-xl">💊</span>
                  </div>
                  <p className="text-slate-300 text-sm font-medium mb-2">Ask anything about medications</p>
                  <p className="text-slate-500 text-xs leading-relaxed max-w-sm">
                    Try: "What drug class is amoxicillin?" or "What are the side effects of ibuprofen?"
                    or "How do ACE inhibitors work?"
                  </p>
                  <div className="flex flex-wrap gap-2 mt-4 justify-center">
                    {[
                      'What is amoxicillin used for?',
                      'How do beta-blockers work?',
                      'What are NSAIDs?',
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setChatInput(suggestion)}
                        className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-full text-slate-400 text-xs hover:text-white hover:border-white/30 transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                chatMessages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {msg.role === 'assistant' && (
                      <div className="w-7 h-7 bg-[#4A9B8E] rounded-full flex items-center justify-center mr-2 mt-0.5 flex-shrink-0">
                        <span className="text-white text-xs font-bold">P</span>
                      </div>
                    )}
                    <div className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-[#4A9B8E] text-white rounded-tr-sm'
                        : 'bg-white/8 border border-white/10 text-slate-300 rounded-tl-sm'
                    }`}>
                      <p className="text-sm leading-relaxed">{msg.role === 'assistant' ? stripMarkdown(msg.content) : msg.content}</p>
                    </div>
                  </div>
                ))
              )}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="w-7 h-7 bg-[#4A9B8E] rounded-full flex items-center justify-center mr-2 flex-shrink-0">
                    <span className="text-white text-xs font-bold">P</span>
                  </div>
                  <div className="bg-white/8 border border-white/10 rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '0ms'}} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '150ms'}} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '300ms'}} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Chat input */}
            <div className="border-t border-white/10 p-4">
              {chatError && (
                <p className="text-red-400 text-xs mb-3">{chatError}</p>
              )}
              <div className="flex gap-3">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleChatSend()}
                  placeholder="Ask about a drug, class, or interaction…"
                  disabled={chatLoading}
                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-[#4A9B8E] focus:ring-1 focus:ring-[#4A9B8E] transition-colors text-sm disabled:opacity-50"
                />
                <button
                  onClick={handleChatSend}
                  disabled={chatLoading || !chatInput.trim()}
                  className="bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
                >
                  Send
                </button>
              </div>
              <p className="text-slate-600 text-xs mt-2">
                Responses are grounded in verified clinical data. Always confirm with your pharmacist.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
