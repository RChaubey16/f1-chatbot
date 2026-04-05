import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'
import { Navbar } from '@/components/layout/Navbar'

const geist = Geist({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'F1 Chatbot',
  description: 'Ask anything about Formula 1 history and the current season',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geist.className} flex flex-col h-screen overflow-hidden`}
        style={{ background: 'var(--f1-bg)' }}>
        <Navbar />
        {children}
      </body>
    </html>
  )
}
