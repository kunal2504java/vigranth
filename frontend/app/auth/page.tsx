"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { Inbox, ArrowRight, Mail } from "lucide-react"
import { useStore } from "@/lib/store"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function AuthPage() {
  const router = useRouter()
  const { login, register, googleAuth } = useStore()
  const [mode, setMode] = useState<"choose" | "login" | "register">("choose")
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  function handleGoogle() {
    googleAuth()
    router.push("/onboarding")
  }

  function handleEmail(e: React.FormEvent) {
    e.preventDefault()
    if (mode === "register") {
      register(name, email, password)
    } else {
      login(email, password)
    }
    router.push("/onboarding")
  }

  return (
    <div className="min-h-screen dot-grid-bg flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-md"
      >
        {/* Logo */}
        <div className="flex items-center gap-3 mb-8">
          <Inbox size={20} strokeWidth={1.5} />
          <span className="text-sm font-mono tracking-[0.15em] uppercase font-bold">
            UNIFYINBOX
          </span>
        </div>

        {/* Auth card */}
        <div className="border-2 border-foreground bg-background p-8">
          <AnimatePresence mode="wait">
            {mode === "choose" ? (
              <motion.div
                key="choose"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <h1 className="text-lg font-mono font-bold tracking-wider uppercase mb-1">
                  Get Started
                </h1>
                <p className="text-xs font-mono text-muted-foreground mb-8">
                  Create an account or log in to continue
                </p>

                {/* Google */}
                <button
                  onClick={handleGoogle}
                  className="w-full flex items-center justify-center gap-3 border-2 border-foreground bg-foreground text-background px-4 py-3 text-xs font-mono tracking-wider uppercase hover:opacity-90 transition-opacity mb-3"
                >
                  <GoogleIcon />
                  Continue with Google
                </button>

                {/* Email */}
                <button
                  onClick={() => setMode("register")}
                  className="w-full flex items-center justify-center gap-3 border-2 border-foreground px-4 py-3 text-xs font-mono tracking-wider uppercase hover:bg-foreground hover:text-background transition-colors mb-8"
                >
                  <Mail size={16} />
                  Continue with Email
                </button>

                <p className="text-[10px] font-mono text-muted-foreground text-center">
                  Already have an account?{" "}
                  <button
                    onClick={() => setMode("login")}
                    className="underline text-foreground hover:text-[#ea580c] transition-colors"
                  >
                    Log in
                  </button>
                </p>
              </motion.div>
            ) : (
              <motion.div
                key="form"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <h1 className="text-lg font-mono font-bold tracking-wider uppercase mb-1">
                  {mode === "register" ? "Create Account" : "Welcome Back"}
                </h1>
                <p className="text-xs font-mono text-muted-foreground mb-6">
                  {mode === "register"
                    ? "Enter your details to get started"
                    : "Enter your credentials to continue"}
                </p>

                <form onSubmit={handleEmail} className="space-y-4">
                  {mode === "register" && (
                    <div>
                      <Label className="text-[10px] font-mono tracking-wider uppercase">
                        Name
                      </Label>
                      <Input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Your name"
                        required
                        className="mt-1.5 font-mono"
                      />
                    </div>
                  )}
                  <div>
                    <Label className="text-[10px] font-mono tracking-wider uppercase">
                      Email
                    </Label>
                    <Input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      required
                      className="mt-1.5 font-mono"
                    />
                  </div>
                  <div>
                    <Label className="text-[10px] font-mono tracking-wider uppercase">
                      Password
                    </Label>
                    <Input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
                      required
                      minLength={8}
                      className="mt-1.5 font-mono"
                    />
                  </div>

                  <button
                    type="submit"
                    className="w-full flex items-center justify-center gap-2 border-2 border-foreground bg-foreground text-background px-4 py-3 text-xs font-mono tracking-wider uppercase hover:opacity-90 transition-opacity"
                  >
                    {mode === "register" ? "Create Account" : "Log In"}
                    <ArrowRight size={14} />
                  </button>
                </form>

                <div className="mt-5 text-center space-y-2">
                  <p className="text-[10px] font-mono text-muted-foreground">
                    {mode === "register" ? (
                      <>
                        Already have an account?{" "}
                        <button
                          onClick={() => setMode("login")}
                          className="underline text-foreground hover:text-[#ea580c]"
                        >
                          Log in
                        </button>
                      </>
                    ) : (
                      <>
                        Don&apos;t have an account?{" "}
                        <button
                          onClick={() => setMode("register")}
                          className="underline text-foreground hover:text-[#ea580c]"
                        >
                          Sign up
                        </button>
                      </>
                    )}
                  </p>
                  <button
                    onClick={() => setMode("choose")}
                    className="text-[10px] font-mono text-muted-foreground underline hover:text-foreground"
                  >
                    Back to options
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  )
}
