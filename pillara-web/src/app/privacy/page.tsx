export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[#0F1B2D] py-16 px-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2 mb-10">
          <div className="w-8 h-8 bg-[#4A9B8E] rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">P</span>
          </div>
          <span className="text-white font-semibold text-lg">Pillara</span>
        </div>

        <h1 className="text-3xl font-bold text-white mb-2">Privacy Policy</h1>
        <p className="text-slate-400 text-sm mb-10">Last updated: August 2026</p>

        <div className="space-y-10 text-slate-300 text-sm leading-7">
          <section>
            <h2 className="text-white font-semibold text-lg mb-3">1. Who We Are</h2>
            <p>Pillara is an AI-powered medication safety platform. We help patients and caregivers manage medications and check for drug interactions.</p>
            <p className="mt-3">Contact us at: <a href="mailto:privacy@pillara.site" className="text-[#4A9B8E] hover:underline">privacy@pillara.site</a></p>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">2. What We Collect</h2>
            <div className="space-y-3">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Account information</p>
                <p>Your email address and a hashed version of your password. We never store your password in plain text.</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Health information</p>
                <p>Medication names, dosages, known allergies, and medical conditions you choose to enter. Used solely to provide medication safety checks and reminders.</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Usage information</p>
                <p>Which features you use, when you use them, and your device&apos;s IP address. Used to improve the service and detect abuse.</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">AI chat content</p>
                <p>Questions you ask the medication assistant are processed by AI providers (Groq, Google). We do not send your name, email, or account details to AI providers.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">3. Where Your Data Is Stored</h2>
            <p>Your data is stored on servers in the <strong className="text-white">United States</strong> (NeonDB on AWS). By using Pillara, you consent to this international transfer. We use HTTPS/TLS encryption in transit and encryption at rest.</p>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">4. Who We Share Data With</h2>
            <div className="space-y-2">
              <p><strong className="text-white">Caregivers you invite:</strong> Can see your medication list per the role you assign.</p>
              <p><strong className="text-white">AI providers (Groq, Google Gemini):</strong> Your questions and drug names are sent for response generation. Your name and email are not sent.</p>
              <p><strong className="text-white">Email provider (Resend):</strong> Your email address and reminder content for delivery.</p>
              <p><strong className="text-white">Error monitoring (Sentry):</strong> Technical errors only — health data is scrubbed before transmission.</p>
              <p><strong className="text-white">We do not sell your data.</strong></p>
            </div>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">5. Your Rights (NDPR)</h2>
            <div className="space-y-3">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Right to access</p>
                <p>View all your data in your dashboard at any time.</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Right to deletion</p>
                <p>Delete your account and all associated data from Settings. Audit logs are retained in pseudonymized form as required by law.</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <p className="text-white font-medium mb-1">Right to correction</p>
                <p>Update your profile, medications, and account details from the dashboard at any time.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">6. Data Retention</h2>
            <ul className="space-y-1 list-disc list-inside">
              <li>Account and health data: retained until you delete your account</li>
              <li>AI conversation history: deleted automatically after 1 hour</li>
              <li>Session tokens: expire after 24 hours</li>
              <li>Audit logs: retained indefinitely in pseudonymized form</li>
            </ul>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">7. Medical Disclaimer</h2>
            <div className="bg-[#F59E0B]/10 border border-[#F59E0B]/30 rounded-xl p-4">
              <p className="text-[#F59E0B] font-medium mb-2">⚠️ Important</p>
              <p>Pillara is an informational tool only. It does not provide medical advice, diagnosis, or treatment. Always consult a qualified healthcare professional before making any decisions about your medications.</p>
            </div>
          </section>

          <section>
            <h2 className="text-white font-semibold text-lg mb-3">8. Contact</h2>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <p><strong className="text-white">Data Protection Officer:</strong> Pillara Health</p>
              <p><strong className="text-white">Email:</strong> <a href="mailto:privacy@pillara.site" className="text-[#4A9B8E] hover:underline">privacy@pillara.site</a></p>
            </div>
          </section>
        </div>

        <div className="mt-16 pt-8 border-t border-white/10">
          <a href="/" className="text-slate-500 hover:text-slate-300 text-sm transition-colors">← Back to Pillara</a>
        </div>
      </div>
    </div>
  )
}