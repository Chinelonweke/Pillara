'use client'
import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Reminder {
  id: string
  medication_id: string
  reminder_time: string
  is_recurring: boolean
  recurrence_rule: string | null
  notify_push: boolean
  notify_email: boolean
  notify_sms: boolean
  is_active: boolean
  next_send_at: string | null
}

interface Medication {
  id: string
  name: string
  dosage: string | null
}

function formatTime(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatNextSend(isoString: string | null): string {
  if (!isoString) return 'One-time (sent)'
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = date.getTime() - now.getTime()
  const diffHours = Math.round(diffMs / (1000 * 60 * 60))
  if (diffHours < 1) return 'Due soon'
  if (diffHours < 24) return `In ${diffHours} hours`
  const diffDays = Math.round(diffHours / 24)
  return `In ${diffDays} day${diffDays !== 1 ? 's' : ''}`
}

function RemindersContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const profileId = searchParams.get('profile_id')

  const [reminders, setReminders] = useState<Reminder[]>([])
  const [medications, setMedications] = useState<Medication[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)

  const [selectedMedId, setSelectedMedId] = useState('')
  const [reminderTime, setReminderTime] = useState('08:00')
  const [isRecurring, setIsRecurring] = useState(true)
  const [frequency, setFrequency] = useState('FREQ=DAILY')
  const [notifyEmail, setNotifyEmail] = useState(true)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')

  const token = typeof window !== 'undefined' ? localStorage.getItem('pillara_access_token') : null
  const headers: Record<string, string> = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [remRes, medRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/reminders/?profile_id=${profileId}`, { headers }),
        fetch(`${API_BASE}/api/v1/medications/?profile_id=${profileId}`, { headers }),
      ])
      if (remRes.ok) setReminders(await remRes.json())
      if (medRes.ok) setMedications(await medRes.json())
    } catch (e) {
      console.error('Failed to load reminders:', e)
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId])

  useEffect(() => {
    if (!profileId) { router.push('/dashboard'); return }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
  }, [profileId, loadData, router])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedMedId) { setAddError('Please select a medication'); return }
    setAdding(true)
    setAddError('')

    const today = new Date()
    const [hours, minutes] = reminderTime.split(':').map(Number)
    today.setHours(hours, minutes, 0, 0)

    if (today < new Date()) {
      today.setDate(today.getDate() + 1)
    }

    try {
      const res = await fetch(`${API_BASE}/api/v1/reminders/?profile_id=${profileId}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          medication_id: selectedMedId,
          reminder_time: today.toISOString(),
          is_recurring: isRecurring,
          recurrence_rule: isRecurring ? frequency : null,
          notify_push: false,
          notify_email: notifyEmail,
          notify_sms: false,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setAddError(data.message || 'Failed to create reminder'); return }
      setReminders(prev => [...prev, data])
      setShowAddForm(false)
      setSelectedMedId('')
      setReminderTime('08:00')
    } catch {
      setAddError('Something went wrong. Please try again.')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (reminderId: string) => {
    if (!confirm('Delete this reminder?')) return
    try {
      await fetch(`${API_BASE}/api/v1/reminders/${reminderId}`, {
        method: 'DELETE',
        headers,
      })
      setReminders(prev => prev.filter(r => r.id !== reminderId))
    } catch (e) {
      console.error('Failed to delete reminder:', e)
    }
  }

  const getMedName = (medId: string) => {
    const med = medications.find(m => m.id === medId)
    return med ? `${med.name}${med.dosage ? ` (${med.dosage})` : ''}` : 'Unknown medication'
  }

  return (
    <div className="min-h-screen bg-[#0F1B2D]">
      <nav className="border-b border-white/10 px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-slate-400 hover:text-white text-sm transition-colors">
              ← Dashboard
            </Link>
            <span className="text-slate-600">|</span>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-[#4A9B8E] rounded-md flex items-center justify-center">
                <span className="text-white font-bold text-xs">P</span>
              </div>
              <span className="text-white font-medium text-sm">Reminders</span>
            </div>
          </div>
          <button
            onClick={() => setShowAddForm(true)}
            className="bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Add reminder
          </button>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-8 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Medication Reminders</h1>
          <p className="text-slate-400 text-sm mt-1">
            Get email reminders to take your medications on time.
          </p>
        </div>

        {showAddForm && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 mb-8">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-white font-semibold">New reminder</h2>
              <button onClick={() => setShowAddForm(false)} className="text-slate-400 hover:text-white text-lg">✕</button>
            </div>

            {addError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">
                <p className="text-red-400 text-sm">{addError}</p>
              </div>
            )}

            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Medication</label>
                {medications.length === 0 ? (
                  <p className="text-slate-500 text-sm">No medications added yet. Add medications from the dashboard first.</p>
                ) : (
                  <select
                    value={selectedMedId}
                    onChange={e => setSelectedMedId(e.target.value)}
                    required
                    className="w-full bg-[#1a2d47] border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-[#4A9B8E] text-sm"
                  >
                    <option value="">Select a medication...</option>
                    {medications.map(med => (
                      <option key={med.id} value={med.id}>
                        {med.name}{med.dosage ? ` — ${med.dosage}` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Time</label>
                <input
                  type="time"
                  value={reminderTime}
                  onChange={e => setReminderTime(e.target.value)}
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-[#4A9B8E] text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Frequency</label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => { setIsRecurring(true); setFrequency('FREQ=DAILY') }}
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isRecurring && frequency === 'FREQ=DAILY'
                        ? 'bg-[#4A9B8E] text-white'
                        : 'bg-white/5 border border-white/10 text-slate-300 hover:border-[#4A9B8E]/50'
                    }`}
                  >
                    Daily
                  </button>
                  <button
                    type="button"
                    onClick={() => { setIsRecurring(true); setFrequency('FREQ=WEEKLY') }}
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      isRecurring && frequency === 'FREQ=WEEKLY'
                        ? 'bg-[#4A9B8E] text-white'
                        : 'bg-white/5 border border-white/10 text-slate-300 hover:border-[#4A9B8E]/50'
                    }`}
                  >
                    Weekly
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsRecurring(false)}
                    className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      !isRecurring
                        ? 'bg-[#4A9B8E] text-white'
                        : 'bg-white/5 border border-white/10 text-slate-300 hover:border-[#4A9B8E]/50'
                    }`}
                  >
                    Once
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-lg px-4 py-3">
                <input
                  type="checkbox"
                  id="notify_email"
                  checked={notifyEmail}
                  onChange={e => setNotifyEmail(e.target.checked)}
                  className="w-4 h-4 accent-[#4A9B8E]"
                />
                <label htmlFor="notify_email" className="text-sm text-slate-300">
                  Send email reminder to my account email
                </label>
              </div>

              <button
                type="submit"
                disabled={adding || medications.length === 0}
                className="w-full bg-[#4A9B8E] hover:bg-[#3d8a7d] disabled:opacity-50 text-white py-3 rounded-lg text-sm font-medium transition-colors"
              >
                {adding ? 'Creating...' : 'Create reminder'}
              </button>
            </form>
          </div>
        )}

        {loading ? (
          <div className="text-slate-400 text-sm text-center py-12">Loading reminders...</div>
        ) : reminders.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-[#4A9B8E] text-2xl">⏰</span>
            </div>
            <h3 className="text-white font-medium mb-2">No reminders yet</h3>
            <p className="text-slate-400 text-sm mb-6">
              Set up reminders to get email notifications when it&apos;s time to take your medications.
            </p>
            <button
              onClick={() => setShowAddForm(true)}
              className="bg-[#4A9B8E] hover:bg-[#3d8a7d] text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Add your first reminder
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {reminders.map(reminder => (
              <div
                key={reminder.id}
                className="bg-white/5 border border-white/10 rounded-xl px-5 py-4 flex items-center justify-between group"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-[#4A9B8E]/10 border border-[#4A9B8E]/20 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-[#4A9B8E] text-lg">⏰</span>
                  </div>
                  <div>
                    <p className="text-white font-medium text-sm capitalize">
                      {getMedName(reminder.medication_id)}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-slate-400 text-xs">
                        {formatTime(reminder.reminder_time)}
                      </span>
                      <span className="text-slate-600 text-xs">·</span>
                      <span className="text-slate-400 text-xs">
                        {reminder.is_recurring
                          ? reminder.recurrence_rule?.includes('DAILY') ? 'Daily' : 'Weekly'
                          : 'One-time'
                        }
                      </span>
                      {reminder.next_send_at && (
                        <>
                          <span className="text-slate-600 text-xs">·</span>
                          <span className="text-[#4A9B8E] text-xs">
                            {formatNextSend(reminder.next_send_at)}
                          </span>
                        </>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      {reminder.notify_email && (
                        <span className="text-xs bg-white/5 border border-white/10 rounded-full px-2 py-0.5 text-slate-400">
                          📧 Email
                        </span>
                      )}
                      {reminder.notify_push && (
                        <span className="text-xs bg-white/5 border border-white/10 rounded-full px-2 py-0.5 text-slate-400">
                          🔔 Push
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(reminder.id)}
                  className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 text-xs transition-all"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

export default function RemindersPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[#0F1B2D] flex items-center justify-center">
        <div className="text-white text-sm">Loading...</div>
      </div>
    }>
      <RemindersContent />
    </Suspense>
  )
}