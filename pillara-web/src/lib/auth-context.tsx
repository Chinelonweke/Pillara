'use client'
// src/lib/auth-context.tsx
// Global auth state — wraps the entire app so any component can
// know if the user is logged in and who they are.

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { auth, UserInfo, setTokens, clearTokens, getToken, TokenResponse } from './api'

interface AuthContextType {
  user: UserInfo | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  // On mount, check if we have a stored token and load user info
  useEffect(() => {
    const token = getToken()
    if (token) {
      auth.me()
        .then(setUser)
        .catch(() => {
          // Token is invalid or expired — clear it
          clearTokens()
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const handleTokenResponse = async (tokenResponse: TokenResponse, redirectTo?: string) => {
    setTokens(tokenResponse.access_token, tokenResponse.refresh_token)
    const userInfo = await auth.me()
    setUser(userInfo)
    return userInfo
  }

  const login = async (email: string, password: string) => {
    const tokenResponse = await auth.login(email, password)
    await handleTokenResponse(tokenResponse)
  }

  const register = async (email: string, password: string) => {
    const tokenResponse = await auth.register(email, password)
    await handleTokenResponse(tokenResponse)
  }

  const logout = async () => {
    try {
      await auth.logout()
    } catch {
      // Logout best-effort — clear local state regardless
    }
    clearTokens()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      register,
      logout,
      isAuthenticated: !!user,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
