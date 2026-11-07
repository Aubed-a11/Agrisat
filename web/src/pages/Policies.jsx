import { useState } from 'react'
import { FilePlus2, Smartphone } from 'lucide-react'
import { api, CROPS, fmt, pct } from '../api'
import { useMeta } from '../main'
import { PageHeader, Section, Field, ErrorBox, Notice, Loading, Status, Stat, useLoad } from '../components/ui'

export default function Policies() {
  const meta = useMeta()
  const list = useLoad(() => meta ? api.get(`/policies?campaign=${meta.campaign}`) : Promise.resolve(null), [meta?.campaign])
  const farmers = useLoad(() => api.get('/farmers'), [])
  const orgs = useLoad(() => api.get('/organisations'), [])
  const [f, setF] = useState({ farmer_id: '', crop: 'mais', product: 'rendement_zone', area_ha: 2, premium_payment_mode: 'mobile_money', credit_amount: '', institution_id: '' })
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)

  const save = async (e) => {
    e.preventDefault(); setErr(null)
    const body = { ...f, campaign: meta.campaign, product: f.crop === 'mais' ? f.product : 'indice_pluie', farmer_id: +f.farmer_id, credit_amount: f.credit_amount ? +f.credit_amount : null, institution_id: f.institution_id ? +f.institution_id : null }
    try { const r = await api.post('/policies', body); setMsg(`Police ${r.number} créée. Part producteur ${fmt(r.premium_farmer)} FCFA.`); list.reload() } catch (x) { setErr(x.message) }
  }
  const collect = async (id) => {
    try { const r = await api.post(`/policies/${id}/collect-premium`); setMsg(r.message || 'Prime encaissée'); list.reload() } catch (x) { setErr(x.message) }
  }
  if (!meta || !list.data) return <Loading />
  const d = list.data
  const tot = (k) => d.reduce((a, p) => a + p[k], 0)
  return (
    <div>
      <PageHeader title={`Polices, campagne ${meta.campaign}`} description="Souscription individuelle ou liée à un crédit intrants. En cas de sinistre, l'indemnité rembourse d'abord l'encours du crédit, puis le solde est versé au producteur." />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Polices" value={fmt(d.length)} sub={`${fmt(d.filter((p) => p.credit).length)} liées à un crédit`} />
        <Stat label="Superficie assurée" value={`${fmt(tot('area_ha'), 1)} ha`} />
        <Stat label="Primes totales" value={`${fmt(tot('premium_total'))} F`} sub={`dont subvention ${fmt(tot('premium_subsidy'))} F`} />
        <Stat label="Primes à encaisser" value={fmt(d.filter((p) => !p.premium_paid).length)} tone="ochre" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <Section title="Souscrire une police">
          <form onSubmit={save} className="space-y-3">
            <Field label="Producteur"><select className="input" required value={f.farmer_id} onChange={(e) => setF({ ...f, farmer_id: e.target.value })}>
              <option value="">Choisir</option>{farmers.data?.map((p) => <option key={p.id} value={p.id}>{p.full_name}, {p.commune}</option>)}</select></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Culture"><select className="input" value={f.crop} onChange={(e) => setF({ ...f, crop: e.target.value })}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Superficie (ha)"><input className="input" type="number" step="0.25" min="0.25" value={f.area_ha} onChange={(e) => setF({ ...f, area_ha: +e.target.value })} /></Field>
            </div>
            {f.crop === 'mais' && <Field label="Produit"><select className="input" value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })}>
              <option value="rendement_zone">Rendement par zone (statistiques DSA)</option><option value="indice_pluie">Indice pluie satellitaire</option></select></Field>}
            <Field label="Crédit intrants lié (FCFA, facultatif)"><input className="input" type="number" value={f.credit_amount} onChange={(e) => setF({ ...f, credit_amount: e.target.value })} /></Field>
            {f.credit_amount && <Field label="Institution de microfinance"><select className="input" value={f.institution_id} onChange={(e) => setF({ ...f, institution_id: e.target.value })}>
              <option value="">Choisir</option>{orgs.data?.filter((o) => o.kind === 'imf').map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>}
            <Field label="Paiement de la part producteur"><select className="input" value={f.premium_payment_mode} onChange={(e) => setF({ ...f, premium_payment_mode: e.target.value })}>
              <option value="mobile_money">Mobile money</option><option value="retenue_credit">Retenue sur le crédit</option></select></Field>
            <button className="btn-primary w-full justify-center"><FilePlus2 size={16} /> Souscrire</button>
            <ErrorBox error={err} /><Notice onClose={() => setMsg(null)}>{msg}</Notice>
          </form>
        </Section>
        <Section title="Polices de la campagne" className="lg:col-span-2">
          <div className="overflow-x-auto max-h-[640px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-white"><tr><th className="th">Police</th><th className="th">Producteur</th><th className="th">Commune</th><th className="th">Culture</th><th className="th">Produit</th><th className="th num">Ha</th><th className="th num">Somme assurée</th><th className="th num">Part producteur</th><th className="th">Crédit</th><th className="th">État</th><th className="th"></th></tr></thead>
              <tbody>{d.map((p) => (
                <tr key={p.id}>
                  <td className="td tabular-nums text-xs whitespace-nowrap">{p.number}</td><td className="td font-semibold">{p.farmer}</td><td className="td">{p.commune}</td><td className="td">{CROPS[p.crop]}</td>
                  <td className="td text-xs">{p.product === 'rendement_zone' ? `Rendement par zone, ${pct(p.coverage, 0)}` : 'Indice pluie'}</td>
                  <td className="td num">{fmt(p.area_ha, 2)}</td><td className="td num">{fmt(p.sum_insured)}</td><td className="td num">{fmt(p.premium_farmer)}</td>
                  <td className="td text-xs">{p.credit ? `${fmt(p.credit.outstanding)} F restants` : ''}</td>
                  <td className="td"><Status value={p.status} /></td>
                  <td className="td">{!p.premium_paid && <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => collect(p.id)}><Smartphone size={13} /> Encaisser</button>}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Section>
      </div>
    </div>
  )
}
