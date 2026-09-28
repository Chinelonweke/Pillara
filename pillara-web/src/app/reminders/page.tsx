'use client'
export const dynamic = 'force-dynamic'  // ← this line added
import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { apiFetch, APIError } from '@/lib/api'

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

function frequencyLabel(reminder: Reminder): string {
  if (!reminder.is_recurring) return 'One-time'
  if (reminder.recurrence_rule?.includes('DAILY')) return 'Daily'
  if (reminder.recurrence_rule?.includes('WEEKLY')) return 'Weekly'
  return 'Recurring'
}

function RemindersContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const profileId = searchParams.get('profile_id')

  const [reminders, setReminders] = useState<Reminder[]>([])
  const [medications, setMedications] = useState<Medication[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)

  // Form state
  const [selectedMedId, setSelectedMedId] = useState('')
  const [times, setTimes] = useState<string[]>(['08:00'])  // Multiple times support
  const [frequency, setFrequency] = useState<'daily' | 'weekly' | 'once'>('daily')
  const [notifyEmail, setNotifyEmail] = useState(true)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [rems, meds] = await Promise.all([
        apiFetch<Reminder[]>(`/api/v1/reminders/?profile_id=${profileId}`),
        apiFetch<Medication[]>(`/api/v1/medications/?profile_id=${profileId}`),
      ])
      setReminders(rems)
      setMedications(meds)
    } catch (e) {
      console.error('Failed to load reminders:', e)
    } finally {
      setLoading(false)
    }
  }, [profileId])

    useEffect(() => {
    if (!profileId) { router.push('/dashboard'); return }
    const fetchData = async () => { await loadData() }
    fetchData().catch(console.error)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, router])

  const addTime = () => {
    setTimes(prev => [...prev, '12:00'])
  }

  const removeTime = (index: number) => {
    if (times.length === 1) return  // Always keep at least one
    setTimes(prev => prev.filter((_, i) => i !== index))
  }

  const updateTime = (index: number, value: string) => {
    setTimes(prev => prev.map((t, i) => i === index ? value : t))
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedMedId) { setAddError('Please select a medication'); return }
    if (times.length === 0) { setAddError('Please add at least one time'); return }

    setAdding(true)
    setAddError('')

    // Create one reminder record per time — this is the correct clinical data model.
    // Each administration time is tracked independently for sending and auditing.
    const recurrenceRule = frequency === 'daily' ? 'FREQ=DAILY'
      : frequency === 'weekly' ? 'FREQ=WEEKLY'
      : null

    const created: Reminder[] = []
    const errors: string[] = []

    for (const time of times) {
      const today = new Date()
      const [hours, minutes] = time.split(':').map(Number)
      today.setHours(hours, minutes, 0, 0)
      if (today < new Date()) {
        today.setDate(today.getDate() + 1)
      }

      try {
        const data = await apiFetch<Reminder>(`/api/v1/reminders/?profile_id=${profileId}`, {
          method: 'POST',
          body: {
            medication_id: selectedMedId,
            reminder_time: today.toISOString(),
            is_recurring: frequency !== 'once',
            recurrence_rule: recurrenceRule,
            notify_push: false,
            notify_email: notifyEmail,
            notify_sms: false,
          },
        })
        created.push(data)
      } catch (err) {
        errors.push(`${time}: ${err instanceof APIError ? err.message : 'Network error'}`)
      }
    }

    if (created.length > 0) {
      setReminders(prev => [...prev, ...created])
    }

    if (errors.length > 0) {
      setAddError(`Some reminders failed: ${errors.join(', ')}`)
    } else {
      setShowAddForm(false)
      setSelectedMedId('')
      setTimes(['08:00'])
      setFrequency('daily')
    }

    setAdding(false)
  }

  const handleDelete = async (reminderId: string) => {
    if (!confirm('Delete this reminder?')) return
    try {
      await apiFetch(`/api/v1/reminders/${reminderId}`, { method: 'DELETE' })
      // Only remove from UI state after server confirms deletion
      setReminders(prev => prev.filter(r => r.id !== reminderId))
    } catch (e) {
      console.error('Failed to delete reminder:', e)
      alert(e instanceof APIError ? e.message : 'Network error. Please check your connection and try again.')
    }
  }

  // Group reminders by medication for cleaner display
  const groupedReminders = medications.reduce<Record<string, Reminder[]>>((acc, med) => {
    const medReminders = reminders.filter(r => r.medication_id === med.id)
    if (medReminders.length > 0) {
      acc[med.id] = medReminders.sort((a, b) =>
        new Date(a.reminder_time).getTime() - new Date(b.reminder_time).getTime()
      )
    }
    return acc
  }, {})

  const timesLabel = (count: number) => `${count} time${count !== 1 ? 's' : ''} daily`

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <nav className="border-b border-[var(--border)] px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">
              ← Dashboard
            </Link>
            <span className="text-slate-600">|</span>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-[var(--primary)] rounded-md flex items-center justify-center">
                <span className="text-[var(--foreground)] font-bold text-xs">P</span>
              </div>
              <span className="text-[var(--foreground)] font-medium text-sm">Reminders</span>
            </div>
          </div>
          <button
            onClick={() => setShowAddForm(true)}
            className="bg-[var(--primary)] hover:bg-[#3d8a7d] text-[var(--foreground)] px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            + Add reminder
          </button>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-8 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[var(--foreground)]">Medication Reminders</h1>
          <p className="text-[var(--muted)] text-sm mt-1">
            Set reminders for each time you need to take your medications. Add multiple times for medications taken more than once daily.
          </p>
        </div>

        {showAddForm && (
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6 mb-8">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[var(--foreground)] font-semibold">New reminder</h2>
              <button onClick={() => { setShowAddForm(false); setTimes(['08:00']); setAddError('') }}
                className="text-[var(--muted)] hover:text-[var(--foreground)] text-lg">✕</button>
            </div>

            {addError && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">
                <p className="text-red-400 text-sm">{addError}</p>
              </div>
            )}

            <form onSubmit={handleAdd} className="space-y-5">

              {/* Medication select */}
              <div>
                <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Medication</label>
                {medications.length === 0 ? (
                  <p className="text-[var(--muted)] text-sm">No medications added yet. Add medications from the dashboard first.</p>
                ) : (
                  <select
                    value={selectedMedId}
                    onChange={e => setSelectedMedId(e.target.value)}
                    required
                    className="w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] focus:outline-none focus:border-[var(--primary)] text-sm"
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

              {/* Frequency */}
              <div>
                <label className="block text-sm font-medium text-[var(--foreground)] mb-2">Frequency</label>
                <div className="flex gap-3">
                  {(['daily', 'weekly', 'once'] as const).map(f => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setFrequency(f)}
                      className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-colors capitalize ${
                        frequency === f
                          ? 'bg-[var(--primary)] text-[var(--foreground)]'
                          : 'bg-[var(--surface)] border border-[var(--border)] text-[var(--foreground)] hover:border-[var(--primary)]/50'
                      }`}
                    >
                      {f === 'once' ? 'One-time' : f.charAt(0).toUpperCase() + f.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Times — multiple support */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-[var(--foreground)]">
                    {frequency === 'once' ? 'Time' : `Times per ${frequency === 'daily' ? 'day' : 'week'}`}
                  </label>
                  {frequency !== 'once' && (
                    <button
                      type="button"
                      onClick={addTime}
                      className="text-xs font-medium text-[var(--primary)] hover:underline"
                    >
                      + Add another time
                    </button>
                  )}
                </div>

                <div className="space-y-2">
                  {times.map((time, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <input
                        type="time"
                        value={time}
                        onChange={e => updateTime(index, e.target.value)}
                        required
                        className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-2.5 text-[var(--foreground)] focus:outline-none focus:border-[var(--primary)] text-sm"
                      />
                      {times.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeTime(index)}
                          className="text-[var(--muted)] hover:text-red-400 text-sm transition-colors px-2"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                {times.length > 1 && (
                  <p className="text-xs text-[var(--muted)] mt-2">
                    {times.length} reminders will be created — one for each time above.
                  </p>
                )}
              </div>

              {/* Email notification */}
              <div className="flex items-center gap-3 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-4 py-3">
                <input
                  type="checkbox"
                  id="notify_email"
                  checked={notifyEmail}
                  onChange={e => setNotifyEmail(e.target.checked)}
                  className="w-4 h-4 accent-[var(--primary)]"
                />
                <label htmlFor="notify_email" className="text-sm text-[var(--foreground)]">
                  Send email reminder to my account email
                </label>
              </div>

              <button
                type="submit"
                disabled={adding || medications.length === 0}
                className="w-full bg-[var(--primary)] hover:bg-[#3d8a7d] disabled:opacity-50 text-[var(--foreground)] py-3 rounded-lg text-sm font-medium transition-colors"
              >
                {adding
                  ? 'Creating...'
                  : times.length > 1
                  ? `Create ${times.length} reminders`
                  : 'Create reminder'
                }
              </button>
            </form>
          </div>
        )}

        {loading ? (
          <div className="text-[var(--muted)] text-sm text-center py-12">Loading reminders...</div>
        ) : reminders.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-16 h-16 bg-[var(--primary)]/10 border border-[var(--primary)]/20 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-[var(--primary)] text-2xl">⏰</span>
            </div>
            <h3 className="text-[var(--foreground)] font-medium mb-2">No reminders yet</h3>
            <p className="text-[var(--muted)] text-sm mb-6">
              Set up reminders to get email notifications when it&apos;s time to take your medications.
            </p>
            <button
              onClick={() => setShowAddForm(true)}
              className="bg-[var(--primary)] hover:bg-[#3d8a7d] text-[var(--foreground)] px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Add your first reminder
            </button>
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedReminders).map(([medId, medReminders]) => {
              const med = medications.find(m => m.id === medId)
              const freqLabel = frequencyLabel(medReminders[0])
              const isDailyMultiple = freqLabel === 'Daily' && medReminders.length > 1

              return (
                <div key={medId} className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl overflow-hidden">
                  {/* Medication header */}
                  <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 bg-[var(--primary)]/10 rounded-full flex items-center justify-center">
                        <span className="text-[var(--primary)] text-base">⏰</span>
                      </div>
                      <div>
                        <p className="text-[var(--foreground)] font-semibold text-sm capitalize">
                          {med?.name || 'Unknown medication'}
                          {med?.dosage ? <span className="font-normal text-[var(--muted)]"> ({med.dosage})</span> : ''}
                        </p>
                        <p className="text-[var(--muted)] text-xs mt-0.5">
                          {freqLabel}
                          {isDailyMultiple ? ` · ${timesLabel(medReminders.length)}` : ''}
                          {medReminders.some(r => r.notify_email) ? ' · 📧 Email' : ''}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Individual times */}
                  <div className="divide-y divide-[var(--border)]">
                    {medReminders.map((reminder, idx) => (
                      <div key={reminder.id} className="px-5 py-3 flex items-center justify-between group">
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-[var(--muted)] w-6 text-right">{idx + 1}.</span>
                          <div>
                            <span className="text-[var(--foreground)] font-medium text-sm">
                              {formatTime(reminder.reminder_time)}
                            </span>
                            {reminder.next_send_at && (
                              <span className="text-[var(--primary)] text-xs ml-2">
                                {formatNextSend(reminder.next_send_at)}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDelete(reminder.id)}
                          className="opacity-0 group-hover:opacity-100 text-[var(--muted)] hover:text-red-400 text-xs transition-all"
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </main>
    </div>
  )
}

export default function RemindersPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="text-[var(--foreground)] text-sm">Loading...</div>
      </div>
    }>
      <RemindersContent />
    </Suspense>
  )
}