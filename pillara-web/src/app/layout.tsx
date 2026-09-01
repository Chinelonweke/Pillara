import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { AuthProvider } from '@/lib/auth-context'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Pillara — Medication Safety Assistant',
  description: 'AI-powered medication safety — drug interaction checking, allergy alerts, and smart reminders.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{__html: `
        (function() {
          try {
            var dark = localStorage.getItem('pillara_dark_mode') === 'true';
            document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
          } catch(e) {}
        })();
      `}} />
      <body className={inter.className}>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}