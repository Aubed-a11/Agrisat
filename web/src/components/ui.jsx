import { useEffect, useState, useCallback } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, X } from 'lucide-react'

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const reload = useCallback(() => {
    setLoading(true)
    return fn().then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, deps) // eslint-disable-line
  useEffect(() => { reload() }, [reload])
  return { data, error, loading, reload, setData }
}

export function PageHeader({ title, description, actions }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-xl lg:text-2xl font-bold text-ink">{title}</h1>
        {description && <p className="text-sm text-ink/65 mt-1 max-w-3xl">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

export function Stat({ label, value, sub, tone }) {
  const color = tone === 'alert' ? 'text-alert-600' : tone === 'ochre' ? 'text-ochre-600' : 'text-ink'
  return (
    <div className="card p-4">
      <div className="text-xs font-semibold text-ink/60">{label}</div>
      <div className={`text-xl lg:text-2xl font-bold mt-1 tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-xs text-ink/55 mt-1">{sub}</div>}
    </div>
  )
}

export function Loading() {
  return <div className="flex items-center gap-2 text-sm text-ink/60 p-6"><Loader2 className="animate-spin" size={16} /> Chargement</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="flex items-start gap-2 rounded-md border border-alert-500/30 bg-alert-500/5 text-alert-600 text-sm p-3"><AlertTriangle size={16} className="mt-0.5 shrink-0" />{error}</div>
}

export function Notice({ children, onClose, tone = 'ok' }) {
  if (!children) return null
  const cls = tone === 'ok' ? 'border-navy-600/30 bg-navy-50 text-navy-800' : 'border-alert-500/30 bg-alert-500/5 text-alert-600'
  const Icon = tone === 'ok' ? CheckCircle2 : AlertTriangle
  return (
    <div className={`flex items-start gap-2 rounded-md border text-sm p-3 ${cls}`}>
      <Icon size={16} className="mt-0.5 shrink-0" /><div className="flex-1">{children}</div>
      {onClose && <button onClick={onClose} aria-label="Fermer"><X size={14} /></button>}
    </div>
  )
}

const STATUS = {
  normal: ['Normal', 'bg-sky-100 text-navy-700 border-sky-300'],
  vigilance: ['Vigilance', 'bg-ochre-500/10 text-ochre-600 border-ochre-500/30'],
  declenche: ['Déclenché', 'bg-alert-500/10 text-alert-600 border-alert-500/30'],
  hors_saison: ['Avant semis', 'bg-mist-100 text-ink/60 border-mist-200'],
  a_valider: ['À valider', 'bg-ochre-500/10 text-ochre-600 border-ochre-500/30'],
  valide: ['Validé', 'bg-navy-50 text-navy-700 border-navy-100'],
  paye: ['Payé', 'bg-navy-700 text-white border-navy-700'],
  echec: ['Échec', 'bg-alert-500/10 text-alert-600 border-alert-500/30'],
  rejete: ['Rejeté', 'bg-mist-100 text-ink/60 border-mist-200'],
  reussi: ['Réussi', 'bg-navy-50 text-navy-700 border-navy-100'],
  en_cours: ['En cours', 'bg-mist-100 text-ink/70 border-mist-200'],
  active: ['Active', 'bg-navy-50 text-navy-700 border-navy-100'],
  en_attente_prime: ['Prime à payer', 'bg-ochre-500/10 text-ochre-600 border-ochre-500/30'],
  ouverte: ['Ouverte', 'bg-mist-100 text-ink/70 border-mist-200'],
  audit: ['Audit terrain', 'bg-ochre-500/10 text-ochre-600 border-ochre-500/30'],
  fondee: ['Fondée', 'bg-alert-500/10 text-alert-600 border-alert-500/30'],
  non_fondee: ['Non fondée', 'bg-mist-100 text-ink/60 border-mist-200'],
  terminee: ['Terminée', 'bg-mist-100 text-ink/70 border-mist-200'],
  a_venir: ['À venir', 'bg-white text-ink/50 border-mist-200'],
  envoye: ['Envoyé', 'bg-navy-50 text-navy-700 border-navy-100'],
}
export function Status({ value }) {
  const [label, cls] = STATUS[value] || [value, 'bg-mist-100 text-ink/70 border-mist-200']
  return <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded border whitespace-nowrap ${cls}`}>{label}</span>
}
export const STATUS_COLOR = { normal: '#5fa8d3', vigilance: '#c4841d', declenche: '#b42318', hors_saison: '#c7d3df' }

export function Field({ label, children, hint }) {
  return <label className="block"><span className="label">{label}</span>{children}{hint && <span className="text-xs text-ink/50 mt-1 block">{hint}</span>}</label>
}

export function Section({ title, children, actions, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {title && <div className="flex flex-wrap gap-2 items-center justify-between px-4 py-3 border-b border-mist-200"><h2 className="font-semibold text-ink">{title}</h2>{actions}</div>}
      <div className="p-4">{children}</div>
    </section>
  )
}
