import { useState } from 'react'
import { PlayCircle, CheckCheck, Send, XCircle, RotateCcw } from 'lucide-react'
import { api, CROPS, fmt, pct, getSession } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Notice, ErrorBox, Loading, Status, Stat, useLoad } from '../components/ui'

export default function Payouts() {
  const meta = useMeta()
  const isInsurer = ['assureur', 'admin'].includes(getSession().user.role)
  const list = useLoad(() => meta ? api.get(`/payouts?campaign=${meta.campaign}`) : Promise.resolve(null), [meta?.campaign])
  const pays = useLoad(() => (isInsurer || getSession().user.role === 'imf') ? api.get('/payments') : Promise.resolve([]), [])
  const [sel, setSel] = useState([])
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const act = async (fn) => {
    setBusy(true); setErr(null)
    try { setMsg(await fn()); setSel([]); list.reload(); pays.reload() } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  if (!meta || !list.data) return <Loading />
  const d = list.data
  const sum = (s) => d.filter((o) => !s || o.status === s).reduce((a, o) => a + o.amount, 0)
  const pending = d.filter((o) => o.status === 'a_valider')
  const toggle = (id) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id])

  return (
    <div>
      <PageHeader title="Indemnités et paiements"
        description="Indice pluie : calcul à la fin de chaque phase. Rendement par zone : calcul dès la publication des statistiques DSA de la campagne. Ensuite, l'assureur valide, puis le paiement part par mobile money. L'encours du crédit intrants est remboursé en priorité."
        actions={isInsurer && <>
          <button className="btn-primary" disabled={busy} onClick={() => act(async () => { const r = await api.post('/payouts/compute', { campaign: meta.campaign }); return `${r.created} indemnités calculées sur ${r.policies_checked} polices actives, ${fmt(r.total_amount)} FCFA.${r.pending ? ` ${r.pending} polices en attente des données de la campagne (statistiques DSA ou climat non encore publiés).` : ''}` })}><PlayCircle size={16} /> Calculer les indemnités</button>
          <button className="btn-ghost" disabled={busy} onClick={() => act(async () => { const r = await api.post('/payouts/pay', {}); return `${r.paid} paiements effectués, ${r.failed} échecs (${r.provider}).` })}><Send size={16} /> Payer les indemnités validées</button>
        </>} />
      <div className="space-y-3 mb-4"><ErrorBox error={err} /><Notice onClose={() => setMsg(null)}>{msg}</Notice></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="À valider" value={`${fmt(sum('a_valider'))} F`} sub={`${pending.length} indemnités`} tone="ochre" />
        <Stat label="Validées, non payées" value={`${fmt(sum('valide'))} F`} />
        <Stat label="Payées" value={`${fmt(sum('paye'))} F`} sub={`dont ${fmt(d.reduce((a, o) => a + (o.status === 'paye' ? o.to_credit : 0), 0))} F au crédit`} />
        <Stat label="Paiements en échec" value={d.filter((o) => o.status === 'echec').length} tone="alert" sub="numéro invalide ou compte inactif" />
      </div>
      <Section title="Indemnités" actions={isInsurer && sel.length > 0 && <div className="flex gap-2">
        <button className="btn-primary !py-1.5" disabled={busy} onClick={() => act(async () => { const r = await api.post('/payouts/validate', { ids: sel }); return `${r.updated} indemnités validées.` })}><CheckCheck size={15} /> Valider ({sel.length})</button>
        <button className="btn-ghost !py-1.5" disabled={busy} onClick={() => act(async () => { const r = await api.post('/payouts/validate', { ids: sel, decision: 'rejete' }); return `${r.updated} indemnités rejetées.` })}><XCircle size={15} /> Rejeter</button>
        {d.some((o) => sel.includes(o.id) && o.status === 'echec') && <button className="btn-ghost !py-1.5" onClick={() => act(async () => { const r = await api.post('/payouts/pay', { ids: sel }); return `${r.paid} relances réussies, ${r.failed} échecs.` })}><RotateCcw size={15} /> Relancer</button>}
      </div>}>
        {d.length === 0 ? <p className="text-sm text-ink/60">Aucune indemnité calculée pour le moment.</p> : (
          <div className="overflow-x-auto max-h-[560px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-white"><tr>
                {isInsurer && <th className="th"><input type="checkbox" checked={pending.length > 0 && pending.every((o) => sel.includes(o.id))} onChange={(e) => setSel(e.target.checked ? pending.map((o) => o.id) : [])} /></th>}
                <th className="th">Police</th><th className="th">Producteur</th><th className="th">Commune</th><th className="th">Culture</th><th className="th num">Phase</th><th className="th num">Indice</th><th className="th num">Seuil</th><th className="th num">Part versée</th><th className="th num">Montant</th><th className="th num">Au crédit</th><th className="th num">Au producteur</th><th className="th">État</th></tr></thead>
              <tbody>{d.map((o) => (
                <tr key={o.id}>
                  {isInsurer && <td className="td">{['a_valider', 'echec'].includes(o.status) && <input type="checkbox" checked={sel.includes(o.id)} onChange={() => toggle(o.id)} />}</td>}
                  <td className="td text-xs tabular-nums whitespace-nowrap">{o.policy_number}</td><td className="td font-semibold">{o.farmer}</td><td className="td">{o.commune}</td><td className="td">{CROPS[o.crop]}</td>
                  <td className="td num">{o.phase === 0 ? 'Rendement' : o.phase}</td><td className="td num">{fmt(o.index_value)} {o.phase === 0 ? 'kg/ha' : 'mm'}</td><td className="td num">{fmt(o.trigger)} {o.phase === 0 ? 'kg/ha' : 'mm'}</td><td className="td num">{pct(o.fraction)}</td>
                  <td className="td num font-semibold">{fmt(o.amount)}</td><td className="td num">{o.to_credit ? fmt(o.to_credit) : ''}</td><td className="td num">{o.to_farmer ? fmt(o.to_farmer) : ''}</td>
                  <td className="td"><Status value={o.status} /></td>
                </tr>))}</tbody>
            </table>
          </div>)}
      </Section>
      {pays.data?.length > 0 && (
        <Section title="Journal des paiements" className="mt-4">
          <div className="overflow-x-auto max-h-[360px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-white"><tr><th className="th">Date</th><th className="th">Type</th><th className="th">Référence</th><th className="th">Téléphone</th><th className="th">Opérateur</th><th className="th num">Montant</th><th className="th num">Tentatives</th><th className="th">État</th><th className="th">Message</th></tr></thead>
              <tbody>{pays.data.map((p) => (
                <tr key={p.id}><td className="td text-xs whitespace-nowrap">{new Date(p.created_at).toLocaleString('fr-FR')}</td><td className="td">{p.kind.replace('_', ' ')}</td>
                  <td className="td text-xs tabular-nums">{p.reference}</td><td className="td tabular-nums">{p.phone || ''}</td><td className="td uppercase text-xs">{p.operator || p.provider}</td>
                  <td className="td num">{fmt(p.amount)}</td><td className="td num">{p.attempts}</td><td className="td"><Status value={p.status} /></td><td className="td text-xs text-ink/65">{p.message}</td></tr>))}</tbody>
            </table>
          </div>
        </Section>)}
    </div>
  )
}
