"use client"

import { motion } from "framer-motion"
import type { ReactNode } from "react"

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description: string
}

export function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center justify-center py-16 px-6 text-center"
    >
      {icon && (
        <div className="text-3xl mb-4 text-muted-foreground">{icon}</div>
      )}
      <p className="text-sm font-mono font-semibold tracking-wider uppercase text-foreground mb-2">
        {title}
      </p>
      <p className="text-xs font-mono text-muted-foreground max-w-sm">
        {description}
      </p>
    </motion.div>
  )
}
