"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export default function Sheet({
  open,
  onClose,
  title,
  children,
  width = "max-w-xl",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduce ? 0 : 0.15 }}
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            className={`fixed inset-y-0 right-0 z-50 flex w-full ${width} flex-col border-l border-border bg-surface shadow-2xl`}
            initial={reduce ? { opacity: 0 } : { x: "100%" }}
            animate={reduce ? { opacity: 1 } : { x: 0 }}
            exit={reduce ? { opacity: 0 } : { x: "100%" }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
              <div className="min-w-0 text-sm font-medium text-text">{title}</div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close panel"
                className="cursor-pointer rounded-lg p-1.5 text-text-muted outline-none hover:bg-surface-2 hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
              >
                <X size={16} />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
