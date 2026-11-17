import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import {
  fetchArchetypes,
  fetchCat1Presets,
  fetchCat2Presets,
  fetchCat3Presets,
  fetchSystemStatus,
  loadCredentials,
  saveCredentials,
} from './api'
import { Cat1Workbench } from './components/Cat1Workbench'
import { Cat2Workbench } from './components/Cat2Workbench'
import { Cat3Workbench } from './components/Cat3Workbench'
import { MatrixHome } from './components/MatrixHome'
import { RoadmapPreview } from './components/RoadmapPreview'
import { TopNavBar } from './components/TopNavBar'
import type {
  ArchetypesCatalogResponse,
  Cat1PresetsResponse,
  Cat2PresetsResponse,
  Cat3PresetsResponse,
  CreditShieldCredentials,
  SystemStatusResponse,
} from './types'

function ArchetypeRouteDispatcher({
  catalog,
  cat1Presets,
  cat2Presets,
  cat3Presets,
  creds,
  onRefreshSystemStatus,
}: {
  catalog: ArchetypesCatalogResponse
  cat1Presets: Cat1PresetsResponse
  cat2Presets: Cat2PresetsResponse
  cat3Presets: Cat3PresetsResponse
  creds: CreditShieldCredentials
  onRefreshSystemStatus: () => void
}) {
  const { id } = useParams<{ id: string }>()
  const numId = Number(id)
  const arch = catalog.archetypes.find((a) => a.id === numId)

  if (!arch) {
    return <Navigate to="/" replace />
  }

  if (arch.id === 1) {
    return (
      <Cat1Workbench
        archetype={arch}
        presetsData={cat1Presets}
        creds={creds}
        onRefreshSystemStatus={onRefreshSystemStatus}
      />
    )
  }

  if (arch.id === 2) {
    return (
      <Cat2Workbench
        archetype={arch}
        presetsData={cat2Presets}
        creds={creds}
        onRefreshSystemStatus={onRefreshSystemStatus}
      />
    )
  }

  if (arch.id === 3) {
    return (
      <Cat3Workbench
        archetype={arch}
        presetsData={cat3Presets}
        creds={creds}
        onRefreshSystemStatus={onRefreshSystemStatus}
      />
    )
  }

  return <RoadmapPreview archetype={arch} />
}

export function App() {
  const [catalog, setCatalog] = useState<ArchetypesCatalogResponse | null>(null)
  const [cat1Presets, setCat1Presets] = useState<Cat1PresetsResponse | null>(null)
  const [cat2Presets, setCat2Presets] = useState<Cat2PresetsResponse | null>(null)
  const [cat3Presets, setCat3Presets] = useState<Cat3PresetsResponse | null>(null)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null)
  const [creds, setCreds] = useState<CreditShieldCredentials>(() => loadCredentials())
  const [bootError, setBootError] = useState<string | null>(null)

  const refreshStatus = useCallback(() => {
    void fetchSystemStatus().then(setSystemStatus).catch(() => {})
  }, [])

  useEffect(() => {
    Promise.all([
      fetchArchetypes(),
      fetchCat1Presets(),
      fetchCat2Presets(),
      fetchCat3Presets(),
      fetchSystemStatus(),
    ])
      .then(([archData, c1Presets, c2Presets, c3Presets, statusData]) => {
        setCatalog(archData)
        setCat1Presets(c1Presets)
        setCat2Presets(c2Presets)
        setCat3Presets(c3Presets)
        setSystemStatus(statusData)
      })
      .catch((err) => {
        setBootError(err instanceof Error ? err.message : 'Failed to load backend metadata.')
      })
  }, [])

  const handleUpdateCreds = (next: CreditShieldCredentials) => {
    setCreds(next)
    saveCredentials(next)
  }

  if (bootError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md rounded-2xl border border-rose-200 bg-white p-6 text-sm text-rose-800 shadow-sm">
          <div className="font-bold">Unable to connect to NovaMart backend</div>
          <p className="mt-1 text-xs">{bootError}</p>
        </div>
      </div>
    )
  }

  if (!catalog || !cat1Presets || !cat2Presets || !cat3Presets) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-xs font-semibold text-slate-600">
        Loading NovaMart AI Workload Matrix...
      </div>
    )
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <TopNavBar
          archetypes={catalog.archetypes}
          creds={creds}
          onUpdateCreds={handleUpdateCreds}
          systemStatus={systemStatus}
        />
        <main>
          <Routes>
            <Route path="/" element={<MatrixHome catalog={catalog} />} />
            <Route
              path="/archetype/:id"
              element={
                <ArchetypeRouteDispatcher
                  catalog={catalog}
                  cat1Presets={cat1Presets}
                  cat2Presets={cat2Presets}
                  cat3Presets={cat3Presets}
                  creds={creds}
                  onRefreshSystemStatus={refreshStatus}
                />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
