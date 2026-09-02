import Link from 'next/link'

export default function TermsPage() {
  return (
    <div className="min-h-screen py-16 px-6 md:px-8" style={{background: "var(--background)"}}>
      <div className="max-w-3xl mx-auto">
        <Link href="/" className="flex items-center gap-2 mb-10">
          <div className="w-8 h-8 bg-[var(--primary)] rounded-lg flex items-center justify-center">
            <span className="text-[var(--foreground)] font-bold text-sm">P</span>
          </div>
          <span className="text-[var(--foreground)] font-semibold text-lg">Pillara</span>
        </Link>

        <h1 className="text-3xl font-bold text-[var(--foreground)] mb-2">Terms of Service</h1>
        <p className="text-[var(--muted)] text-sm mb-10">Last updated: August 2026</p>

        <div className="space-y-10 text-[var(--foreground)] text-sm leading-7">

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">1. Agreement to Terms</h2>
            <p>
              By creating an account on Pillara or using any part of the Pillara service
              (&quot;Service&quot;), you agree to be bound by these Terms of Service (&quot;Terms&quot;).
              If you do not agree to these Terms, do not use the Service.
            </p>
            <p className="mt-3">
              Pillara Health (&quot;we,&quot; &quot;us,&quot; or &quot;our&quot;) operates this Service.
              By using Pillara you also confirm that you are at least 18 years old, or that you are
              using the Service under the supervision of a parent or legal guardian who agrees to these Terms.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">2. What Pillara Is — and Is Not</h2>
            <div className="bg-[#F59E0B]/5 border border-[#FDE68A] rounded-xl p-4 mb-4">
              <p className="text-[#D97706] font-medium mb-2">⚠️ Critical limitation — please read</p>
              <p>
                Pillara is an <strong className="text-[var(--foreground)]">informational tool only</strong>. It does not
                provide medical advice, medical diagnosis, medical treatment, or medical recommendations.
                Information provided by Pillara — whether from the AI assistant, the drug interaction
                checker, or any other feature — is not a substitute for professional medical advice from
                a licensed healthcare provider.
              </p>
            </div>
            <p>
              Always consult a qualified doctor, pharmacist, or other licensed healthcare professional
              before making any decision about your medications. Never delay seeking professional medical
              advice because of something you read on Pillara. Never disregard professional medical advice
              because of something Pillara told you.
            </p>
            <p className="mt-3">
              Pillara&apos;s AI assistant may sometimes produce incorrect, incomplete, or outdated information.
              Drug interactions are complex. The absence of a warning from Pillara does not mean a
              combination is safe. The presence of a warning does not mean you should stop your medication
              without speaking to your doctor first.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">3. What We Actually Built — Feature Detail</h2>
            <p className="mb-4">This section describes what the Service does technically, so you understand its capabilities and limitations:</p>

            <div className="space-y-4">
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">3.1 Drug Interaction Checker</p>
                <p>
                  When you submit a list of medications, Pillara searches a database of 541+ drug knowledge
                  chunks derived from FDA drug label data and RxNorm (US National Library of Medicine) data.
                  It uses hybrid semantic and keyword search, followed by a cross-encoder re-ranking model,
                  to find the most relevant information. A confidence gate (threshold: 0.75) ensures that
                  if relevant verified data is not found at sufficient confidence, the system returns a safe
                  &quot;insufficient data&quot; response rather than guessing.
                </p>
                <p className="mt-2">
                  <strong className="text-[var(--foreground)]">Limitation:</strong> Our drug knowledge database
                  primarily covers US FDA-approved drugs. Coverage of Nigerian-specific brand names and
                  locally manufactured generics may be incomplete. Drug interactions not well-documented
                  in FDA data may not be detected.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">3.2 Allergy Cross-Reactivity Detection</p>
                <p>
                  Pillara checks your stated allergies against a three-layer system: drug class membership
                  (e.g. penicillins), molecular family relationships (e.g. beta-lactams), and known
                  cross-reactive compounds. This runs deterministically — without AI — before the
                  interaction check.
                </p>
                <p className="mt-2">
                  <strong className="text-[var(--foreground)]">Limitation:</strong> Allergy cross-reactivity is
                  medically complex and individual. Our detection covers documented cross-reactivity
                  patterns but cannot account for individual patient sensitivity, undocumented allergies,
                  or novel drug combinations.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">3.3 AI Medication Assistant</p>
                <p>
                  The AI assistant answers medication-related questions using a retrieval-augmented
                  generation (RAG) pipeline. Responses are grounded in verified clinical data retrieved
                  from our database. The system uses multiple AI providers (currently Groq and Google
                  Gemini) as fallbacks for reliability. Off-topic questions (unrelated to medications)
                  are rejected before reaching the AI.
                </p>
                <p className="mt-2">
                  <strong className="text-[var(--foreground)]">Limitation:</strong> AI-generated responses may
                  contain errors. Drug names and questions are sent to third-party AI providers (Groq,
                  Google Gemini) for processing. Your name, email, and account identity are not sent to
                  AI providers, but drug names and your questions are. AI providers&apos; own terms apply
                  to this data.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">3.4 Multi-Patient Profile Sharing</p>
                <p>
                  You can create profiles for patients you manage and invite other users to access those
                  profiles. Roles are: owner (full control), caregiver (can view and add medications),
                  viewer (read only). Access can be revoked at any time by the profile owner.
                </p>
                <p className="mt-2">
                  <strong className="text-[var(--foreground)]">Limitation:</strong> You are responsible for ensuring
                  that anyone you invite to access a profile has appropriate authorization from the patient.
                  Pillara does not verify caregiver-patient relationships.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">3.5 Medication Reminders</p>
                <p>
                  You can configure email reminders for medications. Reminders are processed by an
                  asynchronous background worker. In the event of a technical failure, Pillara runs a
                  missed reminder recovery job every 10 minutes. However, we cannot guarantee 100%
                  reminder delivery.
                </p>
                <p className="mt-2">
                  <strong className="text-[var(--foreground)]">Limitation:</strong> Pillara reminders are not a
                  substitute for proper medication management. Do not rely solely on Pillara reminders
                  for critical medications. Email delivery depends on third-party services and may be
                  subject to spam filtering.
                </p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">4. Account Responsibilities</h2>
            <p>You are responsible for:</p>
            <ul className="space-y-1 list-disc list-inside mt-2">
              <li>Keeping your account credentials confidential</li>
              <li>All activity that occurs under your account</li>
              <li>The accuracy of medication information you enter</li>
              <li>Notifying us immediately if you believe your account has been compromised at security@pillara.site</li>
              <li>Ensuring that anyone you share access with is appropriately authorized</li>
            </ul>
            <p className="mt-3">
              You may not share your account with others. You may not use Pillara to manage medications
              for a patient without appropriate authorization from that patient or their legal guardian.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">5. Prohibited Uses</h2>
            <p>You may not use Pillara to:</p>
            <ul className="space-y-1 list-disc list-inside mt-2">
              <li>Provide medical advice to others as a professional service without appropriate licensure</li>
              <li>Attempt to circumvent rate limits, authentication, or security measures</li>
              <li>Submit false or misleading medication information</li>
              <li>Use automated tools to scrape, abuse, or overload the service</li>
              <li>Attempt to extract, reverse-engineer, or reproduce our drug knowledge database</li>
              <li>Use the service in any way that violates applicable law</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">6. Data and Privacy</h2>
            <p>
              Your use of Pillara is also governed by our{' '}
              <Link href="/privacy" className="text-[var(--primary)] hover:underline">Privacy Policy</Link>,
              which is incorporated into these Terms. The Privacy Policy describes in detail what
              data we collect, how we protect it, and your rights under Nigeria&apos;s Data Protection
              Regulation (NDPR).
            </p>
            <p className="mt-3">
              Key points: your health data is stored on servers in the United States. We do not sell
              your data. You can delete your account and all associated data at any time from Settings.
              Audit logs are retained in pseudonymized form as required by law.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">7. Security Measures</h2>
            <p>We have implemented the following security controls to protect your data:</p>
            <ul className="space-y-1 list-disc list-inside mt-2">
              <li>Passwords are hashed with bcrypt (cost factor 12) — never stored in plain text</li>
              <li>JWT access tokens expire after 30 minutes; refresh tokens after 7 days</li>
              <li>Server-side session validation on every request — logout actually invalidates tokens</li>
              <li>Account lockout after 5 failed login attempts (15-minute lockout)</li>
              <li>Rate limiting: 60 requests/minute general, 20 AI queries/hour per user</li>
              <li>All data transmission encrypted via HTTPS/TLS</li>
              <li>Personal health information scrubbed from error monitoring logs</li>
              <li>Every action on patient data logged in a tamper-evident audit trail</li>
              <li>Role-based access control on all multi-profile features</li>
              <li>IDOR (unauthorized cross-account access) prevention on every endpoint</li>
            </ul>
            <p className="mt-3">
              Despite these measures, no system is perfectly secure. We cannot guarantee that our
              security measures will prevent all unauthorized access. In the event of a data breach,
              we will notify affected users as required by applicable law.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">8. Third-Party Services</h2>
            <p>Pillara uses the following third-party services, each with their own terms:</p>
            <div className="space-y-2 mt-3">
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p><strong className="text-[var(--foreground)]">NeonDB</strong> — PostgreSQL database hosting. Your patient data is stored here. US-based servers.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p><strong className="text-[var(--foreground)]">Groq / Google Gemini</strong> — AI inference providers. Drug names and AI chat content are sent here for processing.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p><strong className="text-[var(--foreground)]">Resend</strong> — Email delivery. Your email address and reminder content are sent here.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p><strong className="text-[var(--foreground)]">Sentry</strong> — Error monitoring. Technical error reports only — health data is scrubbed before transmission.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p><strong className="text-[var(--foreground)]">PostHog</strong> — Usage analytics. Anonymized events only — no personal health data.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">9. Disclaimer of Warranties</h2>
            <p>
              THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTY OF ANY KIND. TO THE FULLEST
              EXTENT PERMITTED BY LAW, WE DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING
              BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
              AND NON-INFRINGEMENT.
            </p>
            <p className="mt-3">
              WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR COMPLETELY
              SECURE. WE DO NOT WARRANT THE ACCURACY, COMPLETENESS, OR TIMELINESS OF ANY INFORMATION
              PROVIDED BY THE SERVICE.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">10. Limitation of Liability</h2>
            <p>
              TO THE FULLEST EXTENT PERMITTED BY APPLICABLE LAW, PILLARA HEALTH SHALL NOT BE LIABLE
              FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING
              BUT NOT LIMITED TO PERSONAL INJURY, PROPERTY DAMAGE, LOSS OF PROFITS, OR ANY HARM
              RESULTING FROM YOUR RELIANCE ON INFORMATION PROVIDED BY THE SERVICE.
            </p>
            <p className="mt-3">
              YOU ACKNOWLEDGE THAT YOUR USE OF THE SERVICE IS AT YOUR OWN RISK AND THAT YOU WILL
              CONSULT A QUALIFIED HEALTHCARE PROFESSIONAL BEFORE ACTING ON ANY INFORMATION PROVIDED
              BY PILLARA.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">11. Changes to Terms</h2>
            <p>
              We may update these Terms from time to time. When we make significant changes, we will
              notify you by email and update the date at the top of this page. Continued use of the
              Service after changes constitutes acceptance of the updated Terms.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">12. Governing Law</h2>
            <p>
              These Terms are governed by the laws of the Federal Republic of Nigeria.
              Any disputes arising from these Terms or your use of the Service shall be subject
              to the jurisdiction of Nigerian courts.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">13. Contact</h2>
            <div className="bg-white border border-[var(--border)] rounded-xl p-4">
              <p><strong className="text-[var(--foreground)]">Legal enquiries:</strong> <a href="mailto:legal@pillara.site" className="text-[var(--primary)] hover:underline">legal@pillara.site</a></p>
              <p><strong className="text-[var(--foreground)]">Privacy and data requests:</strong> <a href="mailto:privacy@pillara.site" className="text-[var(--primary)] hover:underline">privacy@pillara.site</a></p>
              <p><strong className="text-[var(--foreground)]">Security issues:</strong> <a href="mailto:security@pillara.site" className="text-[var(--primary)] hover:underline">security@pillara.site</a></p>
              <p><strong className="text-[var(--foreground)]">General:</strong> <a href="mailto:hello@pillara.site" className="text-[var(--primary)] hover:underline">hello@pillara.site</a></p>
            </div>
          </section>

        </div>

        <div className="mt-16 pt-8 border-t border-[var(--border)] flex gap-6">
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">← Home</Link>
          <Link href="/privacy" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">Privacy Policy</Link>
          <Link href="/about" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">About</Link>
        </div>
      </div>
    </div>
  )
}