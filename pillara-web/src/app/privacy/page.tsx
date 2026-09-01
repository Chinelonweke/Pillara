import Link from 'next/link'

export default function PrivacyPage() {
  return (
    <div className="min-h-screen py-16 px-6 md:px-8" style={{background: "var(--background)"}}>
      <div className="max-w-3xl mx-auto">
        <Link href="/" className="flex items-center gap-2 mb-10">
          <div className="w-8 h-8 bg-[var(--primary)] rounded-lg flex items-center justify-center">
            <span className="text-[var(--foreground)] font-bold text-sm">P</span>
          </div>
          <span className="text-[var(--foreground)] font-semibold text-lg">Pillara</span>
        </Link>

        <h1 className="text-3xl font-bold text-[var(--foreground)] mb-2">Privacy Policy</h1>
        <p className="text-[var(--muted)] text-sm mb-10">Last updated: August 2026</p>

        <div className="space-y-10 text-[var(--foreground)] text-sm leading-7">

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">1. Who We Are</h2>
            <p>
              Pillara Health operates the Pillara medication safety platform at pillara.site.
              We are committed to protecting the privacy and security of your health information.
            </p>
            <p className="mt-3">
              This Privacy Policy applies to all users of Pillara and complies with
              Nigeria&apos;s Data Protection Regulation (NDPR) and relevant international
              data protection standards.
            </p>
            <div className="bg-white border border-[var(--border)] rounded-xl p-4 mt-3">
              <p><strong className="text-[var(--foreground)]">Data Protection Officer:</strong> Pillara Health</p>
              <p><strong className="text-[var(--foreground)]">Email:</strong> <a href="mailto:privacy@pillara.site" className="text-[var(--primary)] hover:underline">privacy@pillara.site</a></p>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">2. What Data We Collect</h2>
            <div className="space-y-3">
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">2.1 Account data</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li>Email address — used for login, reminders, and system notifications</li>
                  <li>Password — stored only as a bcrypt hash (cost factor 12). We never store or see your actual password.</li>
                  <li>Email verification status and timestamp</li>
                  <li>Account creation date</li>
                </ul>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">2.2 Health and medication data</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li>Medication names and dosages you enter</li>
                  <li>Known drug allergies you declare</li>
                  <li>Medical conditions you optionally enter (e.g. diabetes, hypertension)</li>
                  <li>Patient profile names (typically first names or initials)</li>
                  <li>Medication reminder schedules you configure</li>
                </ul>
                <p className="mt-2 text-[var(--muted)] text-xs">
                  This is your most sensitive data. We treat it accordingly — see Section 5 for security details.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">2.3 AI interaction data</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li>Questions you ask the AI medication assistant</li>
                  <li>Drug names from your profile (sent as context to AI providers)</li>
                  <li>AI response quality feedback (thumbs up/down)</li>
                </ul>
                <p className="mt-2 text-[var(--muted)] text-xs">
                  Your name, email, and account identity are never sent to AI providers. Only drug names and your questions are sent.
                </p>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">2.4 Technical and usage data</p>
                <ul className="space-y-1 list-disc list-inside">
                  <li>IP address (used for rate limiting and security)</li>
                  <li>Device type and browser (inferred from User-Agent header)</li>
                  <li>Pages visited and features used (anonymized, via PostHog)</li>
                  <li>Request timestamps</li>
                  <li>Error reports (personal health information scrubbed before transmission to Sentry)</li>
                </ul>
              </div>

              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-2">2.5 Audit log data</p>
                <p>
                  Every action on patient data is recorded in a tamper-evident audit log including:
                  who performed the action, which profile was accessed, what action was taken,
                  the outcome, and the timestamp. This is a security and compliance requirement,
                  not optional. Audit logs are retained in pseudonymized form even after account deletion.
                </p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">3. How We Use Your Data</h2>
            <div className="space-y-2">
              <p><strong className="text-[var(--foreground)]">Providing the service:</strong> Running drug interaction checks, allergy detection, AI queries, reminders, and profile sharing.</p>
              <p><strong className="text-[var(--foreground)]">Security:</strong> Rate limiting, session management, account lockout, IDOR prevention, and fraud detection.</p>
              <p><strong className="text-[var(--foreground)]">Communication:</strong> Sending medication reminders, verification emails, and important account notices.</p>
              <p><strong className="text-[var(--foreground)]">Improving accuracy:</strong> AI feedback (thumbs up/down) is used to identify where our drug knowledge needs improvement. No personal health data is used for AI training without explicit consent.</p>
              <p><strong className="text-[var(--foreground)]">Legal compliance:</strong> Maintaining audit logs as required by applicable law.</p>
            </div>
            <p className="mt-4 text-[var(--muted)] text-xs">
              We do not use your health data for advertising. We do not sell your data. We do not use your data to profile you for commercial purposes.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">4. Who We Share Data With</h2>
            <div className="space-y-3">
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Users you authorize</p>
                <p>If you share a profile, users you invite can see the medication list and health information on that profile, according to the role you assign them. You control this and can revoke access at any time.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">AI providers — Groq and Google Gemini</p>
                <p>Your questions to the AI assistant and drug names from your profile are sent to these providers to generate responses. Your name, email address, and account identity are not included. These providers have their own privacy policies and data processing terms.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">NeonDB — database infrastructure</p>
                <p>Your patient data (medications, allergies, profiles) is stored on NeonDB&apos;s PostgreSQL infrastructure, hosted on AWS in the United States. NeonDB handles data with encryption at rest and in transit.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Resend — email delivery</p>
                <p>Your email address and the content of reminders and system notifications are sent to Resend for delivery.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Sentry — error monitoring</p>
                <p>Technical error reports are sent to Sentry to help us fix bugs. Personal health information (medication names, allergies, medical conditions) is scrubbed from these reports before transmission using a PHI scrubbing layer.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">PostHog — usage analytics</p>
                <p>Anonymized usage events (e.g. &quot;interaction check run&quot;, &quot;reminder set&quot;) are sent to PostHog. No personal health data is included in these events. These help us understand which features are useful.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Law enforcement</p>
                <p>We will disclose your data to law enforcement or regulatory authorities only when required by applicable law, court order, or when we believe in good faith that disclosure is necessary to protect our legal rights, protect your safety or the safety of others, or prevent fraud.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">5. How We Protect Your Data</h2>
            <p className="mb-4">We have implemented the following security measures:</p>
            <div className="space-y-2">
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Password security</p>
                <p>Passwords are hashed with bcrypt (cost factor 12) before storage. The original password is never stored or transmitted after the initial set. Password reset tokens are single-use and expire after 30 minutes.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Session management</p>
                <p>JWT access tokens expire after 30 minutes. Refresh tokens expire after 7 days. All sessions are validated server-side via Redis on every request — logging out actually invalidates your session, not just deletes a cookie. Sessions are revoked across all devices when you change your password or log out from all devices.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Access control</p>
                <p>Every request that accesses patient data verifies that the requesting user has permission for that specific patient&apos;s data (IDOR prevention). Role-based access control limits what caregivers and viewers can do. Rate limiting prevents brute force attacks.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Encryption</p>
                <p>All data in transit is encrypted via HTTPS/TLS. Data at rest is encrypted by NeonDB (AES-256). Redis session data uses password authentication.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">PHI protection in logs</p>
                <p>Before any error or event data leaves our servers to monitoring providers, it passes through a PHI scrubbing layer that removes medication names, allergy information, and medical conditions from log entries.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Audit trail</p>
                <p>Every create, read, update, or delete operation on patient data is recorded in a tamper-evident audit log with user ID, profile ID, action type, outcome, IP address, and timestamp. This log cannot be deleted by users.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-3">
                <p className="text-[var(--foreground)] font-medium text-xs mb-1">Input security</p>
                <p>User input is sanitized before being sent to AI providers (prompt injection defense). AI responses are HTML-stripped before being returned to users (XSS prevention). SQL injection is prevented by using parameterized queries throughout.</p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">6. Data Storage and International Transfer</h2>
            <p>
              Your data is stored on servers located in the <strong className="text-[var(--foreground)]">United States</strong>.
              By creating an account and using Pillara, you consent to this international transfer of your data.
            </p>
            <p className="mt-3">
              We ensure adequate protection for this transfer by:
            </p>
            <ul className="space-y-1 list-disc list-inside mt-2">
              <li>Using NeonDB, which encrypts data at rest (AES-256) and in transit (TLS)</li>
              <li>Limiting access to your data to only those systems and personnel that need it</li>
              <li>Maintaining contractual safeguards with our infrastructure providers</li>
            </ul>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">7. Data Retention</h2>
            <div className="space-y-2">
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">Account and health data</span>
                <span>Retained until you delete your account, at which point it is permanently deleted</span>
              </div>
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">AI conversation history</span>
                <span>Deleted automatically after 1 hour (stored in Redis with TTL)</span>
              </div>
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">Session tokens</span>
                <span>Access tokens expire after 30 minutes; refresh tokens after 7 days</span>
              </div>
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">Audit logs</span>
                <span>Retained indefinitely in pseudonymized form (user UUID only, no personal details after account deletion)</span>
              </div>
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">Error reports</span>
                <span>Retained for 90 days by Sentry, then automatically deleted</span>
              </div>
              <div className="flex gap-4 items-start bg-white border border-[var(--border)] rounded-xl p-3">
                <span className="text-[var(--muted)] text-xs w-40 flex-shrink-0">Analytics events</span>
                <span>Retained for up to 1 year by PostHog (anonymized)</span>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">8. Your Rights Under NDPR</h2>
            <p className="mb-4">Under Nigeria&apos;s Data Protection Regulation, you have the following rights:</p>
            <div className="space-y-3">
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Right to access</p>
                <p>You can view all your data at any time from your dashboard. To request a data export, email privacy@pillara.site and we will provide it within 30 days.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Right to deletion (right to erasure)</p>
                <p>You can permanently delete your account from Settings → Account → Delete Account. This deletes your user account, all profiles you own, all medications, all reminders, and all notifications. Audit logs are retained in pseudonymized form (the UUID points to no personal data after deletion). This is compliant with NDPR.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Right to correction</p>
                <p>You can update your profile, medications, allergies, and account details at any time from the dashboard.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Right to object</p>
                <p>You can stop using the service and delete your account at any time. To object to specific processing activities, contact privacy@pillara.site.</p>
              </div>
              <div className="bg-white border border-[var(--border)] rounded-xl p-4">
                <p className="text-[var(--foreground)] font-medium mb-1">Right to data portability</p>
                <p>Contact privacy@pillara.site to request your data in a machine-readable format.</p>
              </div>
            </div>
            <p className="mt-4">
              To exercise any of these rights, contact us at{' '}
              <a href="mailto:privacy@pillara.site" className="text-[var(--primary)] hover:underline">privacy@pillara.site</a>.
              We will respond within 30 days.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">9. Cookies and Local Storage</h2>
            <p>Pillara uses browser local storage (not cookies) to store your authentication tokens on your device. These tokens are:</p>
            <ul className="space-y-1 list-disc list-inside mt-2">
              <li>Access token — expires after 30 minutes</li>
              <li>Refresh token — expires after 7 days</li>
            </ul>
            <p className="mt-3">
              These are necessary for the service to function and cannot be disabled without logging you out.
              We do not use tracking cookies or third-party advertising cookies.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">10. Children&apos;s Privacy</h2>
            <p>
              Pillara is not directed at children under 18. We do not knowingly collect personal information
              from children under 18. If you are a parent or guardian and believe your child has provided
              us with personal information, contact us at privacy@pillara.site and we will delete it.
            </p>
            <p className="mt-3">
              Pillara can be used to manage medication profiles for children under parental supervision,
              where the parent or guardian creates and controls the account.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">11. Medical Disclaimer</h2>
            <div className="bg-[#FFFBEB] border border-[#FDE68A] rounded-xl p-4">
              <p className="text-[#D97706] font-medium mb-2">⚠️ Important</p>
              <p>
                Pillara is an informational tool only. It does not provide medical advice, diagnosis,
                or treatment. Always consult a qualified healthcare professional — your doctor or
                pharmacist — before making any decisions about your medications. Never disregard
                professional medical advice based on information from Pillara.
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">12. Changes to This Policy</h2>
            <p>
              We may update this Privacy Policy from time to time. When we make significant changes,
              we will notify you by email at least 14 days before the changes take effect and update
              the date at the top of this page. Continued use of Pillara after changes take effect
              constitutes acceptance of the updated policy.
            </p>
          </section>

          <section>
            <h2 className="text-[var(--foreground)] font-semibold text-lg mb-3">13. Contact and Complaints</h2>
            <div className="bg-white border border-[var(--border)] rounded-xl p-4 space-y-2">
              <p><strong className="text-[var(--foreground)]">Privacy questions and data requests:</strong> <a href="mailto:privacy@pillara.site" className="text-[var(--primary)] hover:underline">privacy@pillara.site</a></p>
              <p><strong className="text-[var(--foreground)]">Security issues:</strong> <a href="mailto:security@pillara.site" className="text-[var(--primary)] hover:underline">security@pillara.site</a></p>
              <p><strong className="text-[var(--foreground)]">General:</strong> <a href="mailto:hello@pillara.site" className="text-[var(--primary)] hover:underline">hello@pillara.site</a></p>
            </div>
            <p className="mt-3">
              If you believe we have not handled your personal data properly, you have the right to
              lodge a complaint with the Nigeria Data Protection Bureau (NDPB) at ndpb.gov.ng.
            </p>
          </section>

        </div>

        <div className="mt-16 pt-8 border-t border-[var(--border)] flex flex-wrap gap-6">
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">← Home</Link>
          <Link href="/terms" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">Terms of Service</Link>
          <Link href="/about" className="text-[var(--muted)] hover:text-[var(--foreground)] text-sm transition-colors">About</Link>
        </div>
      </div>
    </div>
  )
}