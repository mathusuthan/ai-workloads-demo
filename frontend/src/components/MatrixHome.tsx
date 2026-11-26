import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Clock, ShieldAlert } from 'lucide-react'
import type { ArchetypesCatalogResponse } from '../types'

interface MatrixHomeProps {
  catalog: ArchetypesCatalogResponse
}

export function MatrixHome({ catalog }: MatrixHomeProps) {
  const { enterprise, autonomy_tiers, token_bands, archetypes, finops_rules } = catalog

  const getArchetypesForCell = (tier: number, band: number) =>
    archetypes.filter((a) => a.matrix_y_tier === tier && a.matrix_x_band === band)

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-7 sm:px-6">
      {/* Executive Banner */}
      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 text-white shadow-md">
        <div className="border-b border-slate-800 px-6 py-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">
          {enterprise.company_name} · {enterprise.tagline}
        </div>
        <div className="flex flex-col justify-between gap-6 px-6 py-6 lg:flex-row lg:items-center">
          <div className="min-w-0 max-w-2xl space-y-2">
            <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
              {enterprise.series_title}
            </h1>
            <p className="text-sm leading-relaxed text-slate-300">
              Why treating every AI initiative like one general-purpose chatbot on the largest model breaks cloud unit
              economics—and how <span className="font-semibold text-white">NovaMart Enterprise</span> matches each
              workload to its calibrated Autonomy Tier, Token Band, and FinOps lever.
            </p>
            <p className="text-xs leading-relaxed text-slate-400">
              These experiments compare system designs (what is asked for, how much context is sent, caching, tools,
              routing between model sizes) in one synthetic lab setup; the results describe those configurations on these
              tasks and are not an assessment of any model.
            </p>
          </div>
          <div className="flex min-w-0 shrink-0 flex-col items-start gap-2 lg:items-end">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Link
                to="/archetype/1"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-blue-600 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-blue-950/50 transition hover:bg-blue-500"
              >
                <span>Launch Category 1 Workbench</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
              <Link
                to="/archetype/2"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-red-600 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-red-950/50 transition hover:bg-red-500"
              >
                <span>Launch Category 2 Studio</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
              <Link
                to="/archetype/3"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-emerald-700 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-emerald-950/50 transition hover:bg-emerald-600"
              >
                <span>Launch Category 3 Desk</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
              <Link
                to="/archetype/4"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-amber-600 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-amber-950/50 transition hover:bg-amber-500"
              >
                <span>Launch Category 4 RAG Lab</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
              <Link
                to="/archetype/5"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-teal-700 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-teal-950/50 transition hover:bg-teal-600"
              >
                <span>Launch Category 5 3-Way ERP Agent</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
              <Link
                to="/archetype/6"
                className="inline-flex items-center justify-between gap-2 rounded-xl bg-violet-700 px-3.5 py-2.5 text-xs font-bold text-white shadow-lg shadow-violet-950/50 transition hover:bg-violet-600"
              >
                <span>Launch Category 6 Swarm Lab</span>
                <ArrowRight className="h-4 w-4 shrink-0" />
              </Link>
            </div>
            <span className="text-[11px] text-slate-400">{enterprise.deck_attribution}</span>
          </div>
        </div>
      </section>

      {/* Calibrated Autonomy × Token Scale Matrix */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-700">
              Calibrated Autonomy × Logarithmic Token Scale Matrix
            </span>
            <h2 className="text-lg font-extrabold text-slate-900">
              Monotonic Token Load (Cat 1 &lt; Cat 2 &lt; Cat 3 &lt; Cat 4 &lt; Cat 5 &lt;&lt; Cat 6) vs. 4 Autonomy Tiers
            </h2>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
            Click any cell to open its NovaMart Demo / Blog Preview
          </span>
        </div>

        <div className="overflow-x-auto pb-2">
          <div className="min-w-[880px]">
            {/* Grid rows: Y = Tier 4 down to Tier 1 */}
            <div className="grid grid-cols-[190px_repeat(5,minmax(0,1fr))] gap-2.5">
              {autonomy_tiers.map((tierRow) => (
                <div key={tierRow.tier} className="contents">
                  <div className="flex flex-col justify-center rounded-xl border border-slate-200 bg-slate-100/90 px-3.5 py-3">
                    <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-900">
                      {tierRow.short}
                    </span>
                    <span className="mt-0.5 text-xs font-medium text-slate-600">
                      {tierRow.label}
                    </span>
                  </div>

                  {token_bands.map((bandCol) => {
                    const cellArchetypes = getArchetypesForCell(tierRow.tier, bandCol.band)
                    return (
                      <div
                        key={`${tierRow.tier}-${bandCol.band}`}
                        className="flex min-h-[108px] flex-col justify-center gap-2 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-2"
                      >
                        {cellArchetypes.map((arch) => (
                          <Link
                            key={arch.id}
                            to={`/archetype/${arch.id}`}
                            className="group block rounded-lg border bg-white p-2.5 shadow-xs transition hover:-translate-y-0.5 hover:shadow-md"
                            style={{ borderLeftWidth: '4px', borderLeftColor: arch.color_hex }}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <span
                                className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-extrabold text-white"
                                style={{ backgroundColor: arch.color_hex }}
                              >
                                {arch.id}
                              </span>
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                                  arch.status === 'live'
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-slate-100 text-slate-600'
                                }`}
                              >
                                {arch.status === 'live' ? 'Live Lab' : `Post #${arch.blog_post_number}`}
                              </span>
                            </div>
                            <div className="mt-1.5 text-xs font-bold leading-snug text-slate-900 group-hover:text-blue-700">
                              {arch.title}
                            </div>
                            <div className="mt-1 font-mono text-[10px] text-slate-500">
                              {arch.token_band}
                            </div>
                          </Link>
                        ))}
                      </div>
                    )
                  })}
                </div>
              ))}

              {/* X-axis headers along bottom */}
              <div className="flex items-center justify-center rounded-xl bg-slate-950 px-3 py-2.5 text-center text-[11px] font-bold uppercase tracking-wider text-slate-300">
                Autonomy \ Scale
              </div>
              {token_bands.map((b) => (
                <div
                  key={b.band}
                  className="rounded-xl border border-slate-200 bg-slate-900 px-3 py-2.5 text-center text-white"
                >
                  <div className="font-mono text-xs font-bold text-blue-300">
                    {b.code}: {b.range}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-300">{b.subtitle}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 6 NovaMart Archetype Cards */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-extrabold text-slate-900">
            The 6 NovaMart Enterprise AI Workloads
          </h2>
          <span className="text-xs text-slate-500">
            {archetypes.every((a) => a.status === 'live')
              ? `All ${archetypes.length} Categories Live`
              : `${archetypes.filter((a) => a.status === 'live').length} of ${archetypes.length} Categories Live`}
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {archetypes.map((arch) => {
            const isLive = arch.status === 'live'
            return (
              <Link
                key={arch.id}
                to={`/archetype/${arch.id}`}
                className="group flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-xs transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className="rounded-md px-2.5 py-1 text-[11px] font-extrabold tracking-wide text-white"
                      style={{ backgroundColor: arch.color_hex }}
                    >
                      {arch.category_label}
                    </span>
                    {isLive ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Interactive Live
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                        <Clock className="h-3 w-3" />
                        Planned · Post #{arch.blog_post_number}
                      </span>
                    )}
                  </div>

                  <h3 className="mt-3 text-base font-extrabold text-slate-900 group-hover:text-blue-700">
                    {arch.title}
                  </h3>
                  <div className="mt-0.5 text-xs font-semibold text-slate-500">
                    {arch.novamart_product_name}
                  </div>
                  <p className="mt-2.5 text-xs leading-relaxed text-slate-600">
                    {arch.novamart_story}
                  </p>
                </div>

                <div className="mt-4 space-y-2.5 border-t border-slate-100 pt-3">
                  <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-2 font-mono text-[11px]">
                    <div>
                      <span className="block text-[10px] text-slate-400">INPUT</span>
                      <span className="font-semibold text-slate-800">{arch.input_profile}</span>
                    </div>
                    <div>
                      <span className="block text-[10px] text-slate-400">OUTPUT</span>
                      <span className="font-semibold text-slate-800">{arch.output_profile}</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-xs font-bold" style={{ color: arch.color_hex }}>
                    <span>
                      {isLive
                        ? arch.id === 1
                          ? 'Open 4-Rung Arena & Batch Lab'
                          : arch.id === 2
                            ? 'Open Without vs With Template Arena & HITL Studio'
                            : arch.id === 3
                              ? 'Open IT & HR Session Caching Desk'
                              : arch.id === 4
                                ? 'Open Multi-Doc RAG & Citations Lab'
                                : arch.id === 5
                                  ? 'Open 3-Way ERP Reconciliation Agent'
                                  : 'Open Multi-Agent Swarm & CpO Lab'
                        : 'Preview Architecture Plan'}
                    </span>
                    <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      </section>

      {/* 3 Matrix-Aligned FinOps Rules */}
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-blue-600" />
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              From Token Volume to ROI
            </span>
            <h2 className="text-lg font-extrabold text-slate-900">
              3 Architectural FinOps Rules by Matrix Tier
            </h2>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {finops_rules.map((rule) => (
            <div
              key={rule.rule_number}
              className="flex flex-col justify-between rounded-xl border border-slate-200 bg-slate-50/70 p-4"
              style={{ borderTopWidth: '4px', borderTopColor: rule.accent }}
            >
              <div>
                <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  {rule.tiers}
                </div>
                <h3 className="mt-1 text-sm font-extrabold text-slate-900">{rule.title}</h3>
                <ul className="mt-2.5 space-y-1.5 text-xs text-slate-700">
                  {rule.bullets.map((b, i) => (
                    <li key={i} className="flex gap-1.5">
                      <span className="font-bold text-slate-400">•</span>
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-4 rounded-lg bg-white px-3 py-2 text-xs font-bold text-slate-900 shadow-2xs ring-1 ring-slate-200">
                {rule.impact}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
