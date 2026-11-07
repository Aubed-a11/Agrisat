import { useState } from 'react'
import { login } from '../api'
import { ErrorBox } from '../components/ui'

const DEMO = [
  ['assureur', 'Assureur'],
  ['coop', 'Agent de coopérative'],
  ['imf', 'Institution de microfinance'],
  ['partenaire', 'MAEP, FNDA, bailleurs'],
  ['admin', 'Administrateur'],
]

export default function Login({ onLogin }) {
  const [u, setU] = useState('assureur')
  const [p, setP] = useState('agrisat2026')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await login(u, p); onLogin() } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10 bg-gradient-to-br from-navy-800 via-navy-600 to-sky-500">
      <div className="w-full max-w-md">
        <form onSubmit={submit} className="card p-6 space-y-4">
          <div className="pb-2">
            <img src="/agrisat-logo.png" alt="AGRISAT" className="h-14 w-auto" />
            <div className="text-sm text-ink/60 mt-2">Assurance agricole indicielle pour le coton et le maïs du Nord Bénin</div>
          </div>
          <h1 className="text-lg font-semibold border-t border-mist-200 pt-4">Connexion</h1>
          <ErrorBox error={err} />
          <label className="block"><span className="label">Identifiant</span><input className="input" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
          <label className="block"><span className="label">Mot de passe</span><input className="input" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
          <button className="btn-primary w-full justify-center" disabled={busy}>Se connecter</button>
        </form>
        <div className="mt-5">
          <div className="text-xs font-semibold text-sky-100 mb-2">Comptes de démonstration, mot de passe agrisat2026</div>
          <div className="grid sm:grid-cols-2 gap-2">
            {DEMO.map(([id, label]) => (
              <button type="button" key={id} onClick={() => setU(id)} className={`text-left text-sm px-3 py-2 rounded-md border bg-white ${u === id ? 'border-sky-400 ring-2 ring-sky-400' : 'border-white/40 hover:bg-mist-100'}`}>
                <div className="font-semibold">{id}</div><div className="text-xs text-ink/60">{label}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
