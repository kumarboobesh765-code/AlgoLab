"use client";

import Link from "next/link";

interface ComingSoonProps {
  title: string;
  description: string;
  expectedIn?: string;
}

export function ComingSoon({ title, description, expectedIn }: ComingSoonProps) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-20 text-center">
      <span className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-medium text-amber-700">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Coming soon
        {expectedIn ? ` · ${expectedIn}` : ""}
      </span>
      <h1 className="mt-5 text-3xl font-bold text-slate-900">{title}</h1>
      <p className="mt-3 text-[14px] leading-relaxed text-slate-600">{description}</p>
      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/welcome"
          className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          ← Back to products
        </Link>
        <Link
          href="/roadmap"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          See the public roadmap
        </Link>
      </div>
    </div>
  );
}
