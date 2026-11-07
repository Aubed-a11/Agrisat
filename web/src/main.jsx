import React, { createContext, useContext, useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import {
  Map, Calculator, Users, FileText, Banknote, LineChart, BarChart3, MessageSquareWarning,
  FileBarChart, MessageSquare, Smartphone, Settings, LogOut, Info, Menu, X, Database,
} from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import './index.css'
import { api, getSession, setSession } from './api'
import Login from './pages/Login'
import Season from './pages/Season'
import Simulator from './pages/Simulator'
import Farmers from './pages/Farmers'
import Policies from './pages/Policies'
import Payouts from './pages/Payouts'
import Actuarial from './pages/Actuarial'
import Models from './pages/Models'
import Claims from './pages/Claims'
import Reports from './pages/Reports'
import Alerts from './pages/Alerts'
import Ussd from './pages/Ussd'
import Admin from './pages/Admin'
import RealData from './pages/RealData'

const MetaCtx = createContext(null)
export const useMeta = () => useContext(MetaCtx)

const NAV = [
  { to: '/saison', label: 'Suivi de saison', icon: Map, roles: '*' },
  { to: '/simulateur', label: 'Simulateur de prime', icon: Calculator, roles: '*' },
  { to: '/producteurs', label: 'Producteurs', icon: Users, roles: ['cooperative', 'imf', 'assureur'] },
  { to: '/polices', label: 'Polices', icon: FileText, roles: ['cooperative', 'imf', 'assureur'] },
  { to: '/indemnites', label: 'Indemnités et paiements', icon: Banknote, roles: ['assureur', 'imf', 'cooperative'] },
  { to: '/actuariat', label: 'Contrats et portefeuille', icon: LineChart, roles: ['assureur', 'partenaire'] },
  { to: '/modeles', label: 'Modèles de rendement', icon: BarChart3, roles: ['assureur', 'partenaire'] },
  { to: '/donnees', label: 'Données réelles', icon: Database, roles: '*' },
  { to: '/reclamations', label: 'Réclamations', icon: MessageSquareWarning, roles: '*' },
  { to: '/rapports', label: 'Rapports', icon: FileBarChart, roles: '*' },
  { to: '/alertes', label: 'Alertes SMS', icon: MessageSquare, roles: ['assureur', 'cooperative'] },
  { to: '/ussd', label: 'Simulateur USSD', icon: Smartphone, roles: '*' },
  { to: '/parametres', label: 'Paramètres et audit', icon: Settings, roles: ['assureur'] },
]
const ROLE = { admin: 'Administrateur', assureur: 'Assureur', cooperative: 'Coopérative', imf: 'Microfinance', partenaire: 'Partenaire public' }
const allowed = (item, role) => role === 'admin' || item.roles === '*' || item.roles.includes(role)

function Sidebar({ role, user, onNavigate }) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-5 h-16 flex items-center gap-3 border-b border-white/10">
        <img src="/agrisat-mark-white.png" alt="" className="h-9 w-auto" />
        <div>
          <div className="font-bold text-lg tracking-wide text-white leading-tight">AGRISAT</div>
          <div className="text-xs text-sky-300">Assurance agricole indicielle</div>
        </div>
      </div>
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV.filter((n) => allowed(n, role)).map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} onClick={onNavigate} className={({ isActive }) =>
            `flex items-center gap-3 mx-2 px-3 py-2 rounded-md text-sm ${isActive ? 'bg-sky-500/20 text-white font-semibold' : 'text-white/75 hover:text-white hover:bg-white/10'}`}>
            <Icon size={17} strokeWidth={1.8} />{label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-white/10 text-sm">
        <div className="font-semibold text-white">{user.full_name}</div>
        <div className="text-sky-300 text-xs">{ROLE[role]}</div>
        <button className="mt-3 flex items-center gap-2 text-white/70 hover:text-white text-xs" onClick={() => { setSession(null); window.location.href = '/' }}>
          <LogOut size={14} /> Se déconnecter
        </button>
      </div>
    </div>
  )
}

function Shell() {
  const s = getSession()
  const [meta, setMeta] = useState(null)
  const [campaign, setCampaign] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { api.get('/meta').then((m) => { setMeta(m); setCampaign(m.campaign) }).catch(() => {}) }, [])
  const ctx = meta ? { ...meta, current_campaign: meta.campaign, campaign: campaign || meta.campaign } : null
  const role = s.user.role
  return (
    <MetaCtx.Provider value={ctx}>
      <div className="min-h-screen lg:flex">
        <aside className="hidden lg:block w-64 shrink-0 bg-gradient-to-b from-navy-800 via-navy-700 to-navy-600 sticky top-0 h-screen">
          <Sidebar role={role} user={s.user} />
        </aside>
        <header className="lg:hidden sticky top-0 z-[1000] h-14 bg-gradient-to-r from-navy-800 to-navy-600 text-white flex items-center justify-between px-4">
          <div className="flex items-center gap-2 font-bold tracking-wide"><img src="/agrisat-mark-white.png" alt="" className="h-7 w-auto" />AGRISAT</div>
          <button className="p-2 -mr-2" aria-label="Menu" onClick={() => setOpen(true)}><Menu size={20} /></button>
        </header>
        {open && (
          <div className="lg:hidden fixed inset-0 z-[1100]">
            <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
            <div className="absolute left-0 top-0 bottom-0 w-72 bg-gradient-to-b from-navy-800 via-navy-700 to-navy-600 shadow-xl">
              <button className="absolute right-3 top-4 p-1 text-white" aria-label="Fermer" onClick={() => setOpen(false)}><X size={18} /></button>
              <Sidebar role={role} user={s.user} onNavigate={() => setOpen(false)} />
            </div>
          </div>
        )}
        <main className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 lg:px-8 py-2 text-xs border-b border-mist-200 bg-white">
            {meta?.data_source === 'synthetique' ? (
              <span className="flex items-start gap-2 text-ochre-600"><Info size={14} className="mt-px shrink-0" /> Démonstration sur données climatiques et de rendement synthétiques.</span>
            ) : (
              <span className="flex items-start gap-2 text-navy-700"><Info size={14} className="mt-px shrink-0" /> Données réelles : pluie CHIRPS par commune, climat NASA POWER, NDVI WFP, rendements du maïs DSA. Coton sans rendements communaux.</span>
            )}
            {meta?.campaigns?.length > 1 && (
              <label className="flex items-center gap-2 text-ink/70">Campagne
                <select className="input !py-1 !w-auto" value={campaign || ''} onChange={(e) => setCampaign(+e.target.value)}>
                  {meta.campaigns.map((c) => <option key={c} value={c}>{c}{c === meta.last_yield_year ? ', statistiques DSA publiées' : c === meta.campaign ? ', en cours' : ''}</option>)}
                </select>
              </label>
            )}
          </div>
          <div className="p-4 lg:p-8 max-w-[1400px]">
            <Routes>
              <Route path="/saison" element={<Season key={`s${campaign}`} />} />
              <Route path="/simulateur" element={<Simulator />} />
              <Route path="/producteurs" element={<Farmers />} />
              <Route path="/polices" element={<Policies key={`p${campaign}`} />} />
              <Route path="/indemnites" element={<Payouts key={`i${campaign}`} />} />
              <Route path="/actuariat" element={<Actuarial />} />
              <Route path="/modeles" element={<Models />} />
              <Route path="/reclamations" element={<Claims />} />
              <Route path="/rapports" element={<Reports key={`r${campaign}`} />} />
              <Route path="/alertes" element={<Alerts />} />
              <Route path="/ussd" element={<Ussd />} />
              <Route path="/parametres" element={<Admin />} />
              <Route path="/donnees" element={<RealData />} />
              <Route path="*" element={<Navigate to="/saison" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </MetaCtx.Provider>
  )
}

function App() {
  const [logged, setLogged] = useState(!!getSession())
  return <BrowserRouter>{logged ? <Shell /> : <Login onLogin={() => setLogged(true)} />}</BrowserRouter>
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
