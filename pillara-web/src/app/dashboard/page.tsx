'use client'
import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { profiles, medications, interactions, ai, Profile, ProfileWithRole, Medication, InteractionCheckResponse, APIError } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[\*\-]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .trim()
}

interface Member {
  email: string
  role: string
  status: string
  user_id: string
}

// Share Panel Modal
function SharePanel({
  profileId,
  profileName,
  userRole,
  onClose,
}: {
  profileId: string
  profileName: string
  userRole: string
  onClose: () => void
}) {
  const token = localStorage.getItem('pillara_access_token')
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }

  const [tab, setTab] = useState<'invite' | 'claim' | 'members'>('members')
  const [members, setMembers] = useState<Member[]>([])
  const [loadingMembers, setLoadingMembers] = useState(true)

  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('viewer')
  const [inviting, setInviting] = useState(false)
  const [inviteMsg, setInviteMsg] = useState('')
  const [inviteError, setInviteError] = useState('')

  const [claimEmail, setClaimEmail] = useState('')
  const [claiming, setClaiming] = useState(false)
  const [claimMsg, setClaimMsg] = useState('')
  const [claimError, setClaimError] = useState('')

  const fetchMembers = useCallback(async () => {
    setLoadingMembers(true)
    try {
      const res = await fetch(`${API_BASE}/api/v1/sharing/${profileId}/members`, { headers: { 'Authorization': `Bearer ${token}` } })
      if (res.ok) setMembers(await res.json())
    } catch {}
    finally { setLoadingMembers(false) }
  }, [profileId, token])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchMembers()
  }, [fetchMembers])

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setInviting(true)
    setInviteError('')
    setInviteMsg('')
    try {
      const res = await fetch(`${API_BASE}/api/v1/sharing/${profileId}/invite`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      })
      const data = await res.json()
      if (!res.ok) { setInviteError(data.message || 'Failed to send invite'); return }
      setInviteMsg(`Invite sent to ${inviteEmail}. They have 7 days to accept.`)
      setInviteEmail('')
      fetchMembers()
    } catch { setInviteError('Something went wrong. Please try again.') }
    finally { setInviting(false) }
  }

  const handleClaimInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setClaiming(true)
    setClaimError('')
    setClaimMsg('')
    try {
      const res = await fetch(`${API_BASE}/api/v1/sharing/${profileId}/send-claim-invite`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ patient_email: claimEmail }),
      })
      const data = await res.json()
      if (!res.ok) { setClaimError(data.message || 'Failed to send claim invite'); return }
      setClaimMsg(`Claim invitation sent to ${claimEmail}. They have 7 days to claim ownership.`)
      setClaimEmail('')
    } catch { setClaimError('Something went wrong. Please try again.') }
    finally { setClaiming(false) }
  }

  const handleRevoke = async (targetUserId: string) => {
    if (!confirm("Revoke this person's access?")) return
    try {
      await fetch(`${API_BASE}/api/v1/sharing/${profileId}/members/${targetUserId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      })
      fetchMembers()
    } catch {}
  }

  const isOwner = userRole === 'owner'

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-2 md:p-4 overflow-y-auto">
      <div className="bg-[var(--background)] border border-[var(--border)] rounded-2xl w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-[var(--foreground)] font-semibold">Share Profile</h2>
            <p className="text-[var(--muted)] text-xs mt-0.5">{profileName} · Your role: <span className="text-[var(--primary)] capitalize">{userRole}</span></p>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors text-xl">✕</button>
        </div>

        <div className="flex border-b border-[var(--border)]">
          {(['members', 'invite', 'claim'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-3 text-sm font-medium transition-colors capitalize ${
                tab === t ? 'text-[var(--primary)] border-b-2 border-[var(--primary)]' : 'text-[var(--muted)] hover:text-[var(--foreground)]'
              }`}
            >
              {t === 'claim' ? 'Send to Patient' : t === 'invite' ? 'Invite Caregiver' : 'Members'}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === 'members' && (
            <div>
              {loadingMembers ? (
                <p className="text-[var(--muted)] text-sm text-center py-4">Loading members...</p>
              ) : members.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-[var(--muted)] text-sm">No one has access to this profile yet.</p>
                  {isOwner && <p className="text-[var(--muted)] text-xs mt-1">Use the tabs above to invite a caregiver or send to a patient.</p>}
                </div>
              ) : (
                <div className="space-y-3">
                  {members.map((m, i) => (
                    <div key={i} className="flex items-center justify-between bg-white border border-[var(--border)] rounded-xl px-4 py-3">
                      <div>
                        <p className="text-[var(--foreground)] text-sm">{m.email || 'Unknown'}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[var(--primary)] text-xs capitalize">{m.role}</span>
                          <span className="text-[var(--muted)] text-xs">·</span>
                          <span className={`text-xs capitalize ${m.status === 'active' ? 'text-green-400' : 'text-yellow-400'}`}>
                            {m.status}
                          </span>
                        </div>
                      </div>
                      {isOwner && m.user_id && (
                        <button
                          onClick={() => handleRevoke(m.user_id)}
                          className="text-[var(--muted)] hover:text-red-400 text-xs transition-colors"
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'invite' && (
            <div>
              {!isOwner ? (
                <p className="text-[var(--muted)] text-sm text-center py-4">Only the profile owner can invite others.</p>
              ) : (
                <>
                  <p className="text-[var(--muted)] text-sm mb-4 leading-relaxed">
                    Invite a caregiver or nurse to access this profile. They&apos;ll receive an email with a link to accept.
                  </p>

                  {inviteMsg && (
                    <div className="bg-[var(--primary)]/10 border border-[var(--primary)]/20 rounded-lg px-4 py-3 mb-4">
                      <p className="text-[var(--primary)] text-sm">✓ {inviteMsg}</p>
                    </div>
                  )}
                  {inviteError && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">
                      <p className="text-red-400 text-sm">{inviteError}</p>
                    </div>
                  )}

                  <form onSubmit={handleInvite} className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Email address</label>
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={e => setInviteEmail(e.target.value)}
                        required
                        placeholder="caregiver@example.com"
                        className="w-full bg-white border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Role</label>
                      <select
                        value={inviteRole}
                        onChange={e => setInviteRole(e.target.value)}
                        className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] focus:outline-none focus:border-[var(--primary)] text-sm"
                      >
                        <option value="caregiver">Caregiver — can view and add medications</option>
                        <option value="viewer">Viewer — read only (e.g. nurse)</option>
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={inviting}
                      className="w-full bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 text-[var(--foreground)] py-2.5 rounded-lg text-sm font-medium transition-colors"
                    >
                      {inviting ? 'Sending invite...' : 'Send invite'}
                    </button>
                  </form>
                </>
              )}
            </div>
          )}

          {tab === 'claim' && (
            <div>
              {!isOwner ? (
                <p className="text-[var(--muted)] text-sm text-center py-4">Only the profile owner can send claim invites.</p>
              ) : (
                <>
                  <p className="text-[var(--muted)] text-sm mb-4 leading-relaxed">
                    Email the patient so they can claim ownership of this profile. They can sign up and take full control, or ignore the email and let you continue managing it.
                  </p>

                  {claimMsg && (
                    <div className="bg-[var(--primary)]/10 border border-[var(--primary)]/20 rounded-lg px-4 py-3 mb-4">
                      <p className="text-[var(--primary)] text-sm">✓ {claimMsg}</p>
                    </div>
                  )}
                  {claimError && (
                    <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">
                      <p className="text-red-400 text-sm">{claimError}</p>
                    </div>
                  )}

                  <form onSubmit={handleClaimInvite} className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Patient&apos;s email address</label>
                      <input
                        type="email"
                        value={claimEmail}
                        onChange={e => setClaimEmail(e.target.value)}
                        required
                        placeholder="patient@example.com"
                        className="w-full bg-white border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] text-sm"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={claiming}
                      className="w-full bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 text-[var(--foreground)] py-2.5 rounded-lg text-sm font-medium transition-colors"
                    >
                      {claiming ? 'Sending...' : 'Send claim invitation'}
                    </button>
                  </form>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Main Dashboard
export default function DashboardPage() {
  const { user, logout, loading: authLoading } = useAuth()
  const router = useRouter()

  const [profile, setProfile] = useState<Profile | null>(null)
  const [allProfiles, setAllProfiles] = useState<ProfileWithRole[]>([])
  const [showProfileSwitcher, setShowProfileSwitcher] = useState(false)
  const [showSharePanel, setShowSharePanel] = useState(false)
  const [meds, setMeds] = useState<Medication[]>([])
  const [loadingData, setLoadingData] = useState(true)

  const [newMedName, setNewMedName] = useState('')
  const [newMedDosage, setNewMedDosage] = useState('')
  const [addingMed, setAddingMed] = useState(false)
  const [addMedError, setAddMedError] = useState('')

  const [checkResult, setCheckResult] = useState<InteractionCheckResponse | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState('')

  const [chatMessages, setChatMessages] = useState<{role: 'user' | 'assistant', content: string}[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [feedbackGiven, setFeedbackGiven] = useState<Record<number, 'helpful' | 'unhelpful'>>({})

  useEffect(() => {
    if (!authLoading && !user) router.push('/login')
    if (!authLoading && user && !user.onboarding_completed) router.push('/onboarding')
  }, [user, authLoading, router])

  useEffect(() => {
    if (!user) return

    const loadData = async () => {
      try {
        const token = localStorage.getItem('pillara_access_token')
        const allRes = await fetch(`${API_BASE}/api/v1/sharing/all`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        if (allRes.ok) setAllProfiles(await allRes.json())

        const profileList = await profiles.list()
        const primaryProfile = profileList.find(p => p.is_primary) || profileList[0]
        if (primaryProfile) {
          setProfile(primaryProfile)
          setMeds(await medications.list(primaryProfile.id))
        }
      } catch (err) {
        console.error('Failed to load profile data:', err)
      } finally {
        setLoadingData(false)
      }
    }

    loadData()
  }, [user])

  const handleDeleteMedication = async (medicationId: string) => {
    try {
      await medications.delete(medicationId)
      setMeds(prev => prev.filter(m => m.id !== medicationId))
      setCheckResult(null)
    } catch (err) {
      console.error('Failed to delete medication:', err)
    }
  }

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
      setAddMedError(err instanceof APIError ? err.message : 'Failed to add medication. Please try again.')
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
      if (drugNames.length < 2) {
        setCheckError('Add at least 2 medications to check for interactions.')
        return
      }
      setCheckResult(await interactions.check(drugNames.slice(0, 10), profile.id))
    } catch (err) {
      setCheckError(err instanceof APIError ? err.message : 'Interaction check failed. Please try again.')
    } finally {
      setChecking(false)
    }
  }

  const switchProfile = async (profileId: string) => {
    setShowProfileSwitcher(false)
    setLoadingData(true)
    try {
      const profileList = await profiles.list()
      const selected = profileList.find((p: Profile) => p.id === profileId)
      if (selected) {
        setProfile(selected)
        setMeds(await medications.list(selected.id))
        setCheckResult(null)
        setChatMessages([])
      }
    } catch (err) {
      console.error('Failed to switch profile:', err)
    } finally {
      setLoadingData(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    router.push('/')
  }

  const handleFeedback = async (messageIndex: number, rating: 'helpful' | 'unhelpful') => {
    setFeedbackGiven(prev => ({ ...prev, [messageIndex]: rating }))
    try {
      const token = localStorage.getItem('pillara_access_token')
      await fetch(`${API_BASE}/api/v1/ai/feedback`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: conversationId, rating }),
      })
    } catch {
      // Feedback failure is non-critical
    }
  }

  const handleChatSend = async () => {
    if (!chatInput.trim() || chatLoading) return
    const userMessage = chatInput.trim()
    setChatInput('')
    setChatError('')
    setChatMessages(prev => [...prev, { role: 'user', content: userMessage }])
    setChatLoading(true)
    setTimeout(() => {
      const el = document.getElementById('chat-messages')
      if (el) el.scrollTop = el.scrollHeight
    }, 50)
    try {
      const result = await ai.query(userMessage, profile?.id, conversationId)
      setConversationId(result.conversation_id)
      setChatMessages(prev => [...prev, { role: 'assistant', content: result.response_text }])
      setTimeout(() => {
        const el = document.getElementById('chat-messages')
        if (el) el.scrollTop = el.scrollHeight
      }, 50)
    } catch (err) {
      setChatError(err instanceof APIError ? err.message : 'Failed to get a response. Please try again.')
      setChatMessages(prev => prev.slice(0, -1))
    } finally {
      setChatLoading(false)
    }
  }

  if (authLoading || loadingData) {
    return (
      <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="text-[var(--muted)] text-sm">Loading your medications...</div>
      </div>
    )
  }

  if (!user) return null

  const currentProfileRole = allProfiles.find((p: ProfileWithRole) => p.id === profile?.id)?.role || 'owner'

  const riskColor = {
    high: 'text-red-400 bg-red-500/10 border-red-500/20',
    moderate: 'text-[#F59E0B] bg-[#F59E0B]/10 border-[#F59E0B]/20',
    low: 'text-green-400 bg-green-500/10 border-green-500/20',
    none: 'text-green-400 bg-green-500/10 border-green-500/20',
    unknown: 'text-[var(--muted)] bg-slate-500/10 border-slate-500/20',
  }

  return (
    <div className="min-h-screen" style={{background: "var(--background)"}}>
      {showSharePanel && profile && (
        <SharePanel
          profileId={profile.id}
          profileName={profile.name}
          userRole={currentProfileRole}
          onClose={() => setShowSharePanel(false)}
        />
      )}

      <nav className="border-b border-[var(--border)] px-4 md:px-8 py-4" style={{background: "var(--surface)"}}>
        <div className="max-w-5xl mx-auto flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-[var(--primary)] rounded-lg flex items-center justify-center">
              <span className="text-[var(--foreground)] font-bold text-xs">P</span>
            </div>
            <span className="text-[var(--foreground)] font-semibold">Pillara</span>

            {allProfiles.length > 0 && (
              <div className="relative ml-4">
                <button
                  onClick={() => setShowProfileSwitcher(!showProfileSwitcher)}
                  className="flex items-center gap-2 bg-white border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm text-[var(--foreground)] hover:bg-[var(--primary-light)] transition-colors"
                >
                  <span className="text-[var(--primary)]">👤</span>
                  <span className="max-w-[120px] truncate">{profile?.name || 'Select profile'}</span>
                  <span className="text-[var(--muted)] text-xs">▾</span>
                </button>

                {showProfileSwitcher && (
                  <div className="absolute top-full left-0 mt-2 w-64 bg-[var(--surface)] border border-[var(--border)] rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="px-3 py-2 border-b border-[var(--border)]">
                      <p className="text-xs text-[var(--muted)] font-medium uppercase tracking-wide">Switch Profile</p>
                    </div>
                    {allProfiles.map((p: ProfileWithRole) => (
                      <button
                        key={p.id}
                        onClick={() => switchProfile(p.id)}
                        className={`w-full flex items-center justify-between px-3 py-2.5 hover:bg-white transition-colors ${
                          profile?.id === p.id ? 'bg-[var(--primary)]/10' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2 text-left">
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                            p.is_shared_with_me ? 'bg-purple-500/20 text-purple-400' : 'bg-[var(--primary)]/20 text-[var(--primary)]'
                          }`}>
                            {p.name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-[var(--foreground)] text-sm font-medium">{p.name}</p>
                            <p className="text-[var(--muted)] text-xs capitalize">
                              {p.is_shared_with_me ? `Shared · ${p.role}` : p.role}
                            </p>
                          </div>
                        </div>
                        {profile?.id === p.id && <span className="text-[var(--primary)] text-xs">✓</span>}
                      </button>
                    ))}
                    <div className="border-t border-[var(--border)] px-3 py-2">
                      <Link
                        href="/onboarding"
                        className="flex items-center gap-2 text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors"
                        onClick={() => setShowProfileSwitcher(false)}
                      >
                        <span>+</span>
                        <span>Add profile</span>
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 md:gap-4">
            {!user.is_verified && (
              <div className="flex items-center gap-2 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-lg px-3 py-1.5">
                <span className="text-[#F59E0B] text-xs">⚠️ Check your email to verify your account</span>
                <button
                  onClick={async () => {
                    const token = localStorage.getItem('pillara_access_token')
                    await fetch(`${API_BASE}/api/v1/auth/resend-verification`, {
                      method: 'POST',
                      headers: { 'Authorization': `Bearer ${token}` },
                    })
                    alert('Verification email sent! Check your inbox.')
                  }}
                  className="text-[#F59E0B] text-xs underline hover:no-underline"
                >
                  Resend
                </button>
              </div>
            )}
            {profile && (
              <Link
                href={`/reminders?profile_id=${profile.id}`}
                className="hidden sm:block text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors"
              >
                Reminders
              </Link>
            )}
            <Link href="/settings" className="hidden sm:block text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">
              Settings
            </Link>
            <button onClick={handleLogout} className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-4 md:px-8 py-6 md:py-10">
        <div className="mb-10 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[var(--foreground)] mb-1">{profile?.name || 'My Medications'}</h1>
            {profile?.known_allergies && (
              <div className="flex items-center gap-2 mt-3">
                <span className="text-xs text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-full px-3 py-1">
                  ⚠️ Allergy: {profile.known_allergies}
                </span>
              </div>
            )}
            {profile?.medical_conditions && (
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs text-[var(--muted)] bg-white border border-[var(--border)] rounded-full px-3 py-1">
                  Condition: {profile.medical_conditions}
                </span>
              </div>
            )}
          </div>

          {profile && (
            <button
              onClick={() => setShowSharePanel(true)}
              className="flex items-center gap-2 bg-white border border-[var(--border)] hover:border-[var(--primary)]/50 rounded-lg px-4 py-2 text-sm text-[var(--foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              <span>🔗</span>
              <span>Share</span>
              <span className="text-xs text-[var(--primary)] capitalize ml-1">({currentProfileRole})</span>
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[var(--foreground)] font-semibold">Current medications</h2>
              <span className="text-[var(--muted)] text-xs">{meds.length} total</span>
            </div>

            <div className="space-y-3 mb-6">
              {meds.length === 0 ? (
                <div className="bg-white border border-[var(--border)] border-dashed rounded-xl p-8 text-center">
                  <p className="text-[var(--muted)] text-sm">No medications added yet.</p>
                  <p className="text-[var(--muted)] text-xs mt-1">Add your first medication below.</p>
                </div>
              ) : (
                meds.map(med => (
                  <div
                    key={med.id}
                    className="bg-white border border-[var(--border)] rounded-xl px-4 py-3 flex items-center justify-between group"
                  >
                    <div>
                      <p className="text-[var(--foreground)] text-sm font-medium capitalize">{med.name}</p>
                      {med.dosage && <p className="text-[var(--muted)] text-xs mt-0.5">{med.dosage}</p>}
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-2 h-2 bg-[var(--primary)] rounded-full" />
                      <button
                        onClick={() => handleDeleteMedication(med.id)}
                        className="opacity-0 group-hover:opacity-100 text-[var(--muted)] hover:text-red-400 transition-all text-xs"
                        title="Remove medication"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="bg-white border border-[var(--border)] rounded-xl p-5">
              <h3 className="text-[var(--foreground)] text-sm font-medium mb-4">Add medication</h3>
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
                  className="w-full bg-white border border-[var(--border)] rounded-lg px-3 py-2.5 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm"
                />
                <input
                  type="text"
                  value={newMedDosage}
                  onChange={(e) => setNewMedDosage(e.target.value)}
                  placeholder="Dosage (optional, e.g. 500mg)"
                  className="w-full bg-white border border-[var(--border)] rounded-lg px-3 py-2.5 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm"
                />
                <button
                  type="submit"
                  disabled={addingMed || !newMedName.trim()}
                  className="w-full bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--foreground)] py-2.5 rounded-lg text-sm font-medium transition-colors"
                >
                  {addingMed ? 'Adding...' : 'Add medication'}
                </button>
              </form>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[var(--foreground)] font-semibold">Safety check</h2>
            </div>

            <div className="bg-white border border-[var(--border)] rounded-xl p-5 mb-4">
              <p className="text-[var(--muted)] text-sm mb-4 leading-relaxed">
                Check all your current medications for dangerous interactions and allergy cross-reactivity.
              </p>
              <button
                onClick={handleInteractionCheck}
                disabled={checking || meds.length === 0}
                className="w-full bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--foreground)] py-3 rounded-lg text-sm font-semibold transition-colors"
              >
                {checking ? 'Checking...' : `Check ${meds.length} medication${meds.length !== 1 ? 's' : ''}`}
              </button>
              {meds.length === 0 && (
                <p className="text-[var(--muted)] text-xs mt-2 text-center">Add at least one medication first.</p>
              )}
            </div>

            {checkError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-4">
                <p className="text-red-400 text-sm">{checkError}</p>
              </div>
            )}

            {checkResult && (
              <div className="space-y-4">
                <div className={`border rounded-xl px-4 py-3 ${riskColor[checkResult.overall_risk as keyof typeof riskColor] || riskColor.unknown}`}>
                  <p className="text-xs font-medium uppercase tracking-wide mb-1 opacity-70">Overall risk</p>
                  <p className="font-semibold capitalize">{checkResult.overall_risk}</p>
                </div>

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
                        <p className="text-[var(--foreground)] text-sm font-medium capitalize mb-1">{warning.drug_name} — {warning.allergen} allergy</p>
                        <p className="text-[var(--foreground)] text-xs leading-relaxed mb-2">{warning.description}</p>
                        <p className="text-[#F59E0B] text-xs font-medium">{warning.action_required}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                  <p className="text-[var(--foreground)] text-xs font-medium mb-3 uppercase tracking-wide">Analysis</p>
                  <p className="text-[var(--foreground)] text-sm leading-7">{stripMarkdown(checkResult.summary)}</p>
                </div>

                <p className="text-[var(--muted)] text-xs leading-relaxed px-1">{checkResult.disclaimer}</p>

                <div className="flex items-center gap-2 px-1">
                  <div className={`w-2 h-2 rounded-full ${checkResult.confidence_gate_passed ? 'bg-[var(--primary)]' : 'bg-slate-500'}`} />
                  <p className="text-[var(--muted)] text-xs">
                    {checkResult.confidence_gate_passed
                      ? 'Response grounded in verified clinical data'
                      : 'Insufficient verified data — consult your pharmacist'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="mt-10">
          <div className="bg-[var(--surface)] border border-[var(--primary)]/20 rounded-xl px-4 py-3 mb-4 flex items-start gap-3">
            <span className="text-[var(--primary)] text-sm mt-0.5 flex-shrink-0">ℹ️</span>
            <p className="text-[var(--muted)] text-xs leading-relaxed">
              <strong className="text-[var(--foreground)]">Informational use only.</strong>{' '}
              Pillara provides medication information and is not a substitute for professional medical advice.
              Always consult your doctor or pharmacist before making any medication decisions.{' '}
              <a href="/privacy" className="text-[var(--primary)] hover:underline">Privacy Policy</a>
            </p>
          </div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-[var(--foreground)] font-semibold">Ask the medication assistant</h2>
              <p className="text-[var(--muted)] text-xs mt-1">Ask about drug classes, adverse effects, interactions, or how medications work.</p>
            </div>
          </div>

          <div className="rounded-xl overflow-hidden" style={{background: "var(--surface)", border: "1px solid var(--border)", boxShadow: "var(--shadow)"}}>
            <div className="h-64 md:h-80 overflow-y-auto p-4 space-y-4" id="chat-messages">
              {chatMessages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-4 md:px-8">
                  <div className="w-12 h-12 bg-[var(--primary)]/10 border border-[var(--primary)]/20 rounded-full flex items-center justify-center mb-4">
                    <span className="text-[var(--primary)] text-xl">💊</span>
                  </div>
                  <p className="text-[var(--foreground)] text-sm font-medium mb-2">Ask anything about medications</p>
                  <p className="text-[var(--muted)] text-xs leading-relaxed max-w-sm">
                    Try: &quot;What drug class is amoxicillin?&quot; or &quot;What are the side effects of ibuprofen?&quot;
                  </p>
                  <div className="flex flex-wrap gap-2 mt-4 justify-center">
                    {['What is amoxicillin used for?', 'How do beta-blockers work?', 'What are NSAIDs?'].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setChatInput(suggestion)}
                        className="px-3 py-1.5 bg-white border border-[var(--border)] rounded-full text-[var(--muted)] text-xs hover:text-[var(--foreground)] hover:border-white/30 transition-colors"
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
                      <div className="w-7 h-7 bg-[var(--primary)] rounded-full flex items-center justify-center mr-2 mt-0.5 flex-shrink-0">
                        <span className="text-[var(--foreground)] text-xs font-bold">P</span>
                      </div>
                    )}
                    <div className="flex flex-col gap-1">
                      <div className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                        msg.role === 'user'
                          ? 'bg-[var(--primary)] text-[var(--foreground)] rounded-tr-sm'
                          : 'bg-white border border-[var(--border)] text-[var(--foreground)] rounded-tl-sm'
                      }`}>
                        <p className="text-sm leading-relaxed">{stripMarkdown(msg.content)}</p>
                      </div>
                      {msg.role === 'assistant' && (
                        <div className="flex items-center gap-2 ml-1">
                          {feedbackGiven[i] ? (
                            <span className="text-xs text-[var(--muted)]">
                              {feedbackGiven[i] === 'helpful' ? '👍 Thanks!' : '👎 Noted'}
                            </span>
                          ) : (
                            <>
                              <button
                                onClick={() => handleFeedback(i, 'helpful')}
                                className="text-[var(--muted)] hover:text-green-400 text-xs transition-colors"
                                title="Helpful"
                              >
                                👍
                              </button>
                              <button
                                onClick={() => handleFeedback(i, 'unhelpful')}
                                className="text-[var(--muted)] hover:text-red-400 text-xs transition-colors"
                                title="Not helpful"
                              >
                                👎
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="w-7 h-7 bg-[var(--primary)] rounded-full flex items-center justify-center mr-2 flex-shrink-0">
                    <span className="text-[var(--foreground)] text-xs font-bold">P</span>
                  </div>
                  <div className="bg-white border border-[var(--border)] rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '0ms'}} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '150ms'}} />
                      <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{animationDelay: '300ms'}} />
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-[var(--border)] p-4">
              {chatError && <p className="text-red-400 text-xs mb-3">{chatError}</p>}
              <div className="flex gap-3">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleChatSend()}
                  placeholder="Ask about a drug, class, or interaction..."
                  disabled={chatLoading}
                  className="flex-1 bg-white border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] placeholder-slate-500 focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)] transition-colors text-sm disabled:opacity-50"
                />
                <button
                  onClick={handleChatSend}
                  disabled={chatLoading || !chatInput.trim()}
                  className="bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--foreground)] px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
                >
                  Send
                </button>
              </div>
              <p className="text-[var(--muted)] text-xs mt-2">
                Responses are grounded in verified clinical data. Always confirm with your pharmacist.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}