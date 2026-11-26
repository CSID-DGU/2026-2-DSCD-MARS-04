import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

export const supabase = url && key ? createClient(url, key) : null

export const signIn = () =>
  supabase?.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${window.location.origin}/?start=1` } })
