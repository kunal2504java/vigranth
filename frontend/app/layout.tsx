import type { Metadata, Viewport } from 'next'
import { JetBrains_Mono } from 'next/font/google'
import { GeistPixelGrid } from 'geist/font/pixel'
import { ThemeProvider } from '@/components/theme-provider'
import { StoreProvider } from '@/lib/store'
import { Toaster } from '@/components/ui/sonner'

import './globals.css'

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
})

export const metadata: Metadata = {
  title: 'UnifyInbox | AI-Native Universal Communication OS',
  description:
    'UnifyInbox consolidates every messaging platform into a single intelligent feed. Gmail, Slack, Discord, Telegram — ranked by AI priority, enriched with context, and actionable without switching tabs. Read, triage, and reply from one place.',
  keywords: [
    'unified inbox',
    'AI communication',
    'message prioritization',
    'Gmail integration',
    'Slack integration',
    'Discord integration',
    'Telegram integration',
    'AI draft reply',
    'cross-platform messaging',
    'message triage',
    'priority inbox',
    'AI email assistant',
    'unified messaging',
    'communication OS',
    'smart inbox',
    'message classification',
    'productivity tool',
    'context switching',
  ],
  authors: [{ name: 'UnifyInbox' }],
  creator: 'UnifyInbox Inc.',
  publisher: 'UnifyInbox Inc.',
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  openGraph: {
    type: 'website',
    locale: 'en_US',
    title: 'UnifyInbox | AI-Native Universal Communication OS',
    description:
      'Stop context-switching across 6+ messaging apps. UnifyInbox connects Gmail, Slack, Discord, and Telegram into one AI-ranked priority feed. Draft replies with AI, send without leaving.',
    siteName: 'UnifyInbox',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'UnifyInbox | All Your Messages. One Intelligent Feed.',
    description:
      'AI-native unified inbox for Gmail, Slack, Discord, Telegram. Priority-ranked feed, AI draft replies, cross-platform send. Never miss what matters.',
    creator: '@unifyinbox',
  },
  category: 'technology',
}

export const viewport: Viewport = {
  themeColor: '#F2F1EA',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${jetbrainsMono.variable} ${GeistPixelGrid.variable}`} suppressHydrationWarning>
      <body className="font-mono antialiased">
        <StoreProvider>
          <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
            {children}
            <Toaster
              position="bottom-right"
              toastOptions={{
                className: "font-mono border-2 border-foreground text-xs tracking-wider",
              }}
            />
          </ThemeProvider>
        </StoreProvider>
      </body>
    </html>
  )
}
