"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Small permanent contextual-help popover — click a "?" to reveal a short
 * explanation, click elsewhere to dismiss. Deliberately terse (a sentence
 * or two); the guided tour is where the longer explanations live.
 */
export function InfoTooltip({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <span ref={ref} className="relative inline-block">
      <button
        type="button"
        aria-label={title}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] leading-none"
        style={{
          background: "var(--bg-panel-raised)",
          color: "var(--text-faint)",
          border: "1px solid var(--border)",
        }}
      >
        ?
      </button>
      {open ? (
        <div
          className="panel p-2.5"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            width: 220,
            zIndex: 500,
            border: "1px solid var(--border)",
            boxShadow: "0 6px 16px rgba(0,0,0,0.4)",
          }}
        >
          <p className="text-[11px] font-medium mb-1">{title}</p>
          <p className="text-[11px] text-[var(--text-dim)] leading-relaxed">{children}</p>
        </div>
      ) : null}
    </span>
  );
}
