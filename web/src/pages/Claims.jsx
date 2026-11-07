import { useState } from 'react'
import { Send } from 'lucide-react'
import { api, CROPS, getSession } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Field, ErrorBox, Notice, Loading, Status, useLoad } from '../components/ui'

export default function Claims() {
  const meta = useMeta()
  const isInsurer = ['assureur', 'admin'].includes(getSession().user.role)
  const list = useLoad(() => api.get('/claims'), [])
  const [f, setF] = useState({ commune_id: 1, crop: 'coton', description: '', estimated_loss_pct: 40 })
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const save = async (e) => {
    e.preventDefault(); setErr(null)
    try {
      const r = await api.post('/claims', f)
      setMsg(r.audit_triggered ? `Réclamation enregistrée. Seuil atteint (${r.claims_in_commune} réclamations pour ${r.insured_in_commune} polices) : audit de terrain déclenché dans la commune.` : 'Réclamation enregistrée.')
      setF({ ...f, description: '' }); list.reload()
    } catch (x) { setErr(x.message) }
  }
  const decide = async (id, status) => {
    const audit_result = window.prompt('Résultat de l\'audit de terrain') || ''
    await api.post(`/claims/${id}/decision`, { status, audit_result }); list.reload()
  }
  if (!meta) return <Loading />
  return (
    <div>
      <PageHeader title="Réclamations" description="Un producteur perd sa récolte sans être indemnisé : c'est le risque de base. Chaque signalement est enregistré, et au delà d'un seuil par commune un audit de terrain par échantillon est déclenché pour recalibrer le contrat." />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <Section title="Signaler une perte non indemnisée">
          <form onSubmit={save} className="space-y-3">
            <Field label="Commune"><select className="input" value={f.commune_id} onChange={(e) => setF({ ...f, commune_id: +e.target.value })}>{meta.communes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="Culture"><select className="input" value={f.crop} onChange={(e) => setF({ ...f, crop: e.target.value })}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="Perte estimée (%)"><input className="input" type="number" min="0" max="100" value={f.estimated_loss_pct} onChange={(e) => setF({ ...f, estimated_loss_pct: +e.target.value })} /></Field>
            <Field label="Description"><textarea className="input" rows={4} required value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Cause observée, parcelles touchées, dates" /></Field>
            <button className="btn-primary w-full justify-center"><Send size={16} /> Enregistrer</button>
            <ErrorBox error={err} /><Notice onClose={() => setMsg(null)}>{msg}</Notice>
          </form>
        </Section>
        <Section title="Réclamations reçues" className="lg:col-span-2">
          {list.data?.length === 0 ? <p className="text-sm text-ink/60">Aucune réclamation.</p> : (
            <table className="w-full">
              <thead><tr><th className="th">Date</th><th className="th">Commune</th><th className="th">Culture</th><th className="th">Canal</th><th className="th num">Perte</th><th className="th">Description</th><th className="th">État</th>{isInsurer && <th className="th"></th>}</tr></thead>
              <tbody>{list.data?.map((c) => (
                <tr key={c.id}><td className="td text-xs whitespace-nowrap">{new Date(c.created_at).toLocaleDateString('fr-FR')}</td><td className="td">{c.commune}</td><td className="td">{CROPS[c.crop]}</td>
                  <td className="td uppercase text-xs">{c.channel}</td><td className="td num">{c.estimated_loss_pct != null ? `${c.estimated_loss_pct} %` : ''}</td>
                  <td className="td text-sm">{c.description}{c.audit_result && <div className="text-xs text-ink/60 mt-1">Audit : {c.audit_result}</div>}</td>
                  <td className="td"><Status value={c.status} /></td>
                  {isInsurer && <td className="td whitespace-nowrap">{['ouverte', 'audit'].includes(c.status) && <>
                    <button className="text-xs font-semibold text-alert-600 mr-3" onClick={() => decide(c.id, 'fondee')}>Fondée</button>
                    <button className="text-xs font-semibold text-ink/60" onClick={() => decide(c.id, 'non_fondee')}>Non fondée</button></>}</td>}
                </tr>))}</tbody>
            </table>)}
        </Section>
      </div>
    </div>
  )
}
