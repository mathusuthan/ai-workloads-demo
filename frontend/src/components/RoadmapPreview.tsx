import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, BookOpen, Clock, Layers } from 'lucide-react'
import type { ArchetypeSpec } from '../types'

interface RoadmapPreviewProps {
  archetype: ArchetypeSpec
}

export function RoadmapPreview({ archetype }: RoadmapPreviewProps) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Matrix Overview
        </Link>

        <Link
          to="/archetype/1"
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-700"
        >
          <span>Open Live Category 1 Lab</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div
          className="flex flex-wrap items-center justify-between gap-2 px-6 py-3 text-white"
          style={{ backgroundColor: archetype.color_hex }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-extrabold uppercase tracking-wider">
              {archetype.category_label} · {archetype.autonomy_tier_label}
            </span>
            <span className="rounded bg-white/20 px-2 py-0.5 font-mono text-[11px] font-bold">
              {archetype.token_band}
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-950/35 px-3 py-1 text-xs font-bold">
            <Clock className="h-3.5 w-3.5" />
            Planned for Blog Post #{archetype.blog_post_number}
          </span>
        </div>

        <div className="space-y-6 p-6 sm:p-8">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              {archetype.title}
            </h1>
            <p className="mt-1 text-sm font-semibold text-slate-500">
              NovaMart Workload: {archetype.novamart_product_name}
            </p>
            <p className="mt-3 text-sm leading-relaxed text-slate-700">
              {archetype.novamart_story}
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Typical Input Profile
              </div>
              <div className="mt-1 font-mono text-lg font-extrabold text-slate-900">
                {archetype.input_profile}
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Typical Output Profile
              </div>
              <div className="mt-1 font-mono text-lg font-extrabold text-slate-900">
                {archetype.output_profile}
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Tokenomics Dynamics
              </div>
              <div className="mt-1 font-mono text-sm font-extrabold text-slate-900">
                {archetype.dynamics}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5 text-white">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-300">
              <Layers className="h-4 w-4" />
              Architectural FinOps Lever (Blog Post #{archetype.blog_post_number} Thesis)
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-200">
              {archetype.architectural_lever}
            </p>
          </div>

          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Enterprise Use Cases Covered in Deck
            </h2>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {archetype.deck_use_cases.map((uc) => (
                <span
                  key={uc}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-800"
                >
                  <BookOpen className="h-3.5 w-3.5 text-slate-400" />
                  {uc}
                </span>
              ))}
            </div>
          </div>
        </div>
      </article>
    </div>
  )
}
