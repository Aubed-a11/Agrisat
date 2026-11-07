import { useEffect, useState } from 'react'
import { Save } from 'lucide-react'
import { api, getSession, fmt } from '../api'
import { PageHeader, Section, Field, ErrorBox, Notice, Loading, useLoad } from '../components/ui'

export default function Admin() {
  const isAdmin = getSession().user.role === 'admin'
  const st = useLoad(() => api.get('/settings'), [])
  const log = useLoad(() => api.get('/audit'), [])
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { if (st.data) setF(st.data) }, [st.data])
  if (!f) return <Loading />
  const save = async () => {
    setErr(null)
    try {
      await api.put('/settings', { subsidy_rate: +f.subsidy_rate, expense_rate: +f.expense_rate, cost_of_capital: +f.cost_of_capital,
        claims_audit_threshold: +f.claims_audit_threshold, sum_insured_ha: { coton: +f.sum_insured_ha.coton, mais: +f.sum_insured_ha.mais } })
      setMsg('Paramètres enregistrés. Ils s\'appliquent aux nouvelles cotations et souscriptions.'); log.reload()
    } catch (x) { setErr(x.message) }
  }
  const num = (k, label, hint, step = 0.01) => (
    <Field label={label} hint={hint}><input className="input" type="number" step={step} disabled={!isAdmin} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)
  return (
    <div>
      <PageHeader title="Paramètres et journal d'audit" description="Les paramètres de campagne se modifient sans toucher au code. Toute modification de paramètre, souscription, validation et paiement est journalisée." />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Section title="Paramètres de campagne">
          <div className="space-y-3">
            {num('subsidy_rate', 'Taux de subvention publique', 'Part de la prime commerciale prise en charge par l\'État')}
            {num('expense_rate', 'Taux de frais de gestion et de distribution')}
            {num('cost_of_capital', 'Taux de coût du capital')}
            {num('claims_audit_threshold', 'Seuil de déclenchement des audits', 'Part des assurés d\'une commune ayant réclamé')}
            <Field label="Somme assurée coton (FCFA par ha)"><input className="input" type="number" step="5000" disabled={!isAdmin} value={f.sum_insured_ha.coton} onChange={(e) => setF({ ...f, sum_insured_ha: { ...f.sum_insured_ha, coton: e.target.value } })} /></Field>
            <Field label="Somme assurée maïs (FCFA par ha)"><input className="input" type="number" step="5000" disabled={!isAdmin} value={f.sum_insured_ha.mais} onChange={(e) => setF({ ...f, sum_insured_ha: { ...f.sum_insured_ha, mais: e.target.value } })} /></Field>
            {isAdmin ? <button className="btn-primary w-full justify-center" onClick={save}><Save size={16} /> Enregistrer</button>
              : <p className="text-xs text-ink/60">Modification réservée à l'administrateur.</p>}
            <ErrorBox error={err} /><Notice onClose={() => setMsg(null)}>{msg}</Notice>
          </div>
        </Section>
        <Section title="Journal d'audit" className="lg:col-span-2">
          <div className="overflow-x-auto max-h-[620px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-white"><tr><th className="th">Date</th><th className="th">Utilisateur</th><th className="th">Action</th><th className="th">Objet</th><th className="th">Détail</th></tr></thead>
              <tbody>{log.data?.map((a) => (
                <tr key={a.id}><td className="td text-xs whitespace-nowrap">{new Date(a.created_at).toLocaleString('fr-FR')}</td><td className="td">{a.username}</td><td className="td">{a.action.replaceAll('_', ' ')}</td>
                  <td className="td text-xs tabular-nums">{a.target}</td><td className="td text-xs text-ink/60">{a.after ? Object.entries(a.after).map(([k, v]) => `${k} ${typeof v === 'number' ? fmt(v, v % 1 ? 2 : 0) : typeof v === 'object' ? '' : v}`).join(', ') : ''}</td></tr>))}</tbody>
            </table>
          </div>
        </Section>
      </div>
    </div>
  )
}
